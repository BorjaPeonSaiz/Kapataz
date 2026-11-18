"""Agregado Quote con versiones (RF-PR-01 a RF-PR-07, RN-06, RN-07, RN-F-13).

Estados (RF-PR-04): borrador → enviado → aceptado / rechazado / caducado, y
desde aceptado → facturado parcialmente → facturado. Modificar un presupuesto
enviado crea una nueva versión; un borrador se edita sobre su versión.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.calculation import line_base
from kapataz.domain.billing.codes import LineOrigin, RecipientType
from kapataz.domain.billing.errors import (
    InvalidQuoteError,
    InvalidQuoteTransitionError,
    QuoteNotEditableError,
)
from kapataz.domain.billing.ids import QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.line_item import MAX_LINE_DESCRIPTION_LENGTH, LineItem
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.customers.model import CustomerId

# RN-07: con menos de tres muestras no se propone un precio de forma automática.
MIN_HISTORY_SAMPLES = 3
_REDUCED_ELIGIBLE = frozenset({RecipientType.PRIVATE, RecipientType.COMMUNITY})


class PriceSourceKind(StrEnum):
    """Origen del precio de una línea (RN-06)."""

    CATALOG = "catalog"
    HISTORY_MEDIAN = "history_median"
    SIMILAR_QUOTE = "similar_quote"
    MANUAL = "manual"
    NONE = "none"


@dataclass(frozen=True, slots=True, kw_only=True)
class PriceSource:
    """De dónde sale un precio: catálogo, mediana del histórico, presupuesto parecido o a mano.

    ``reference_id`` es el concepto del catálogo o el presupuesto parecido que
    se cita; ``sample_count``, las muestras de la mediana (RN-07).
    """

    kind: PriceSourceKind
    sample_count: int | None = None
    reference_id: UUID | None = None

    def __post_init__(self) -> None:
        needs_reference = self.kind in {PriceSourceKind.CATALOG, PriceSourceKind.SIMILAR_QUOTE}
        if needs_reference != (self.reference_id is not None):
            msg = "Solo el catálogo y un presupuesto parecido, y siempre, se citan."
            raise InvalidQuoteError(msg)
        is_median = self.kind is PriceSourceKind.HISTORY_MEDIAN
        if is_median != (self.sample_count is not None):
            raise InvalidQuoteError("Solo la mediana del histórico, y siempre, lleva sus muestras.")
        if self.sample_count is not None and self.sample_count < MIN_HISTORY_SAMPLES:
            msg = f"Con menos de {MIN_HISTORY_SAMPLES} muestras no se propone precio (RN-07)."
            raise InvalidQuoteError(msg)

    @classmethod
    def manual(cls) -> Self:
        return cls(kind=PriceSourceKind.MANUAL)

    @classmethod
    def none(cls) -> Self:
        return cls(kind=PriceSourceKind.NONE)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteLine:
    """Línea de presupuesto. Puede quedar sin precio si no hay origen (RN-06)."""

    id: QuoteLineId
    description: str
    quantity: Quantity
    unit_price: Money | None
    price_source: PriceSource
    discount: Percentage | None = None
    is_material: bool = False
    outside_works: bool = False

    def __post_init__(self) -> None:
        if (
            not self.description.strip()
            or self.description != self.description.strip()
            or len(self.description) > MAX_LINE_DESCRIPTION_LENGTH
        ):
            raise InvalidQuoteError("Una línea necesita una descripción válida.")
        if (self.unit_price is None) != (self.price_source.kind is PriceSourceKind.NONE):
            raise InvalidQuoteError("Una línea sin origen de precio queda sin precio (RN-06).")
        if self.is_material and self.outside_works:
            raise InvalidQuoteError("Una línea fuera de la obra no puede ser material de la obra.")
        # Una base que pasa del máximo de Money se rechaza al crear la línea.
        _ = self.priced_base

    @property
    def is_priced(self) -> bool:
        return self.unit_price is not None

    @property
    def priced_base(self) -> Money | None:
        if self.unit_price is None:
            return None
        return line_base(self.quantity, self.unit_price, self.discount)

    @property
    def counts_for_works(self) -> bool:
        return not self.outside_works

    def to_invoice_line(self) -> LineItem:
        """Línea de factura que cita esta línea del presupuesto (RF-FA-03)."""
        if self.unit_price is None:
            raise InvalidQuoteError("Una línea sin precio no se puede facturar.")
        return LineItem(
            description=self.description,
            quantity=self.quantity,
            unit_price=self.unit_price,
            discount=self.discount,
            is_material=self.is_material,
            outside_works=self.outside_works,
            origin=LineOrigin.QUOTE,
            quote_line_id=self.id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteVersion:
    """Versión de un presupuesto, con los datos para decidir el IVA de la obra (RN-F-13)."""

    id: QuoteVersionId
    version: int
    lines: tuple[QuoteLine, ...]
    recipient_type: RecipientType
    dwelling_over_two_years: bool | None
    valid_until: date | None
    created_at: datetime

    def __post_init__(self) -> None:
        if self.version < 1:
            raise InvalidQuoteError("Las versiones se numeran desde 1.")
        if self.recipient_type in _REDUCED_ELIGIBLE and self.dwelling_over_two_years is None:
            msg = "Con un particular o una comunidad hay que saber si la vivienda tiene dos años."
            raise InvalidQuoteError(msg)
        ids = [line.id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise InvalidQuoteError("Las líneas de una versión no se repiten.")
        if self.created_at.tzinfo is None:
            raise InvalidQuoteError("La fecha de la versión debe llevar zona horaria.")
        _ = self.base

    @property
    def is_fully_priced(self) -> bool:
        return all(line.is_priced for line in self.lines)

    @property
    def base(self) -> Money:
        """Base presupuestada, con las líneas que tienen precio."""
        return sum_money(base for line in self.lines if (base := line.priced_base) is not None)


class QuoteStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    PARTIALLY_INVOICED = "partially_invoiced"
    INVOICED = "invoiced"


_ACCEPTED_STATES = frozenset({QuoteStatus.ACCEPTED, QuoteStatus.PARTIALLY_INVOICED})


@dataclass(frozen=True, slots=True, kw_only=True)
class Quote:
    """Presupuesto (``Quote``). Es una referencia, no un tope (RN-F-11)."""

    id: QuoteId
    tenant_id: TenantId
    customer_id: CustomerId
    number: DocumentNumber
    status: QuoteStatus
    versions: tuple[QuoteVersion, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.versions:
            raise InvalidQuoteError("Un presupuesto tiene al menos una versión.")
        if [v.version for v in self.versions] != list(range(1, len(self.versions) + 1)):
            raise InvalidQuoteError("Las versiones son consecutivas desde 1.")

    @property
    def current_version(self) -> QuoteVersion:
        return self.versions[-1]

    @property
    def is_billable(self) -> bool:
        """RF-PR-07: solo un presupuesto aceptado se factura."""
        return self.status in _ACCEPTED_STATES

    @property
    def revision_number(self) -> int:
        """Número que debe llevar la versión que se pase a ``revise``."""
        current = self.current_version.version
        return current + 1 if self.status is QuoteStatus.SENT else current

    def revise(self, version: QuoteVersion) -> Self:
        """Cambia el contenido (RF-PR-04).

        Un borrador sustituye su versión actual. Un enviado añade una versión
        nueva y vuelve a borrador, porque esa versión aún no la ha visto el
        cliente. Aceptado, rechazado, caducado o facturado ya no se edita: los
        cambios de la obra van en la factura (RF-FA-12).
        """
        if self.status not in {QuoteStatus.DRAFT, QuoteStatus.SENT}:
            msg = "Este presupuesto ya no se edita; los cambios van en la factura."
            raise QuoteNotEditableError(msg)
        if version.version != self.revision_number:
            msg = f"La versión nueva debe ser la {self.revision_number}."
            raise InvalidQuoteError(msg)
        if self.status is QuoteStatus.DRAFT:
            return replace(self, versions=(*self.versions[:-1], version))
        return replace(self, versions=(*self.versions, version), status=QuoteStatus.DRAFT)

    def send(self) -> Self:
        self._require(QuoteStatus.DRAFT)
        current = self.current_version
        if not current.lines or not current.is_fully_priced:
            raise InvalidQuoteError("No se envía un presupuesto vacío o con líneas sin precio.")
        return replace(self, status=QuoteStatus.SENT)

    def accept(self) -> Self:
        self._require(QuoteStatus.SENT)
        return replace(self, status=QuoteStatus.ACCEPTED)

    def reject(self) -> Self:
        self._require(QuoteStatus.SENT)
        return replace(self, status=QuoteStatus.REJECTED)

    def expire(self, today: date) -> Self:
        """Caduca un enviado cuya validez ya pasó; ``today`` sale del Clock."""
        self._require(QuoteStatus.SENT)
        valid_until = self.current_version.valid_until
        if valid_until is None or today <= valid_until:
            raise InvalidQuoteTransitionError("El presupuesto sigue en su plazo de validez.")
        return replace(self, status=QuoteStatus.EXPIRED)

    def mark_partially_invoiced(self) -> Self:
        """Tras emitir un anticipo o una certificación (RF-PR-04)."""
        self._require(*_ACCEPTED_STATES)
        return replace(self, status=QuoteStatus.PARTIALLY_INVOICED)

    def mark_invoiced(self) -> Self:
        """Tras emitir la factura completa o la fase final, aunque haya diferencia (RN-F-12)."""
        self._require(*_ACCEPTED_STATES)
        return replace(self, status=QuoteStatus.INVOICED)

    def _require(self, *allowed: QuoteStatus) -> None:
        if self.status not in allowed:
            msg = f"No se puede pasar desde el estado «{self.status}»."
            raise InvalidQuoteTransitionError(msg)
