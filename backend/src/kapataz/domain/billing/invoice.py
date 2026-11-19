"""Agregados Invoice y CorrectiveInvoice (RF-FA-01 a RF-FA-05, RF-FA-10, RF-FA-15, RN-F-02 a 06).

Una factura nace como borrador editable y pasa a emitida con ``issue()``. Una
emitida no se modifica (RN-F-02): cualquier cambio lanza
``InvoiceAlreadyIssuedError`` y se corrige con una rectificativa
(``CorrectiveInvoice``), que es también una factura, con su serie y su número.

Los importes no se guardan en la entidad: salen siempre de las líneas con el
cálculo del dominio (``calculation``), así no pueden desfasarse.

Las comprobaciones van en dos grupos:

- **Estructura:** lo que una factura necesita para tener sentido y para que
  sus importes se puedan calcular (estado coherente, fase y anticipo, citas de
  la rectificativa, importes dentro de ``Money``). Vale siempre.
- **Reglas de emisión:** lo que la normativa o la política vigente exige para
  emitir (RN-F-06, RN-F-13, RF-FA-15 y los límites de longitud). Se aplican al
  crear y editar el borrador y otra vez al emitir, pero no al leer una factura
  ya emitida: si una regla se endurece, lo emitido antes tiene que seguir
  leyéndose para consultarlo, exportarlo y rectificarlo (RN-F-02).
"""

from collections.abc import Iterable
from dataclasses import InitVar, dataclass, replace
from datetime import date, datetime
from typing import Self

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.aeat_limits import MAX_DESCRIPTION_LENGTH
from kapataz.domain.billing.calculation import (
    InvoiceTotals,
    totals_from_gross,
    totals_from_lines,
)
from kapataz.domain.billing.codes import (
    CorrectionType,
    InvoiceStatus,
    InvoiceType,
    LineOrigin,
    PhaseType,
    RecipientType,
)
from kapataz.domain.billing.errors import (
    InvalidDocumentNumberError,
    InvalidInvoiceError,
    InvoiceAlreadyIssuedError,
    IssuedAmountsMismatchError,
    MissingIssueDataError,
    NegativeInvoiceBaseError,
)
from kapataz.domain.billing.ids import InvoiceId, QuoteVersionId
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series, check_issue_date
from kapataz.domain.billing.party import Party
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import RegimeKey, TaxRate, VatTreatment
from kapataz.domain.billing.works_vat import material_share
from kapataz.domain.customers.model import CustomerId

_REDUCED_ELIGIBLE = frozenset({RecipientType.PRIVATE, RecipientType.COMMUNITY})
# RF-FA-15: la garantía solo en la factura completa o en la fase final.
_GUARANTEE_PHASES = frozenset({PhaseType.FULL, PhaseType.FINAL})
# Fases en las que las líneas son la obra entera y el 40 % se puede comprobar.
# La certificación solo lleva una parte y el anticipo no lleva trabajos.
_WHOLE_WORKS_PHASES = frozenset({PhaseType.FULL, PhaseType.FINAL})


@dataclass(frozen=True, slots=True, kw_only=True)
class Guarantee:
    """Garantía (``Guarantee``, RF-FA-15): porcentaje de la base cuyo cobro se aplaza.

    No es la retención de IRPF (``Withholding``).
    """

    rate: Percentage
    due_date: date

    def __post_init__(self) -> None:
        if self.rate.is_zero() or self.rate.value >= 100:  # noqa: PLR2004
            raise InvalidInvoiceError("La garantía es un porcentaje mayor que 0 y menor que 100.")


@dataclass(frozen=True, slots=True, kw_only=True)
class IssuedAmounts:
    """Importes de una factura emitida tal como se guardaron al emitirla (RN-F-02).

    Son la prueba de integridad al leerla: tienen que coincidir al céntimo con
    los que el dominio calcula de sus líneas.
    """

    base: Money
    tax: Money
    total_amount: Money
    withholding: Money
    guarantee: Money
    amount_due: Money

    def differences(self, totals: InvoiceTotals) -> tuple[str, ...]:
        """Nombres de los importes guardados que no cuadran con los calculados."""
        pairs = (
            ("base", self.base, totals.base),
            ("tax", self.tax, totals.tax),
            ("total_amount", self.total_amount, totals.total_amount),
            ("withholding", self.withholding, totals.withholding),
            ("guarantee", self.guarantee, totals.guarantee),
            ("amount_due", self.amount_due, totals.amount_due),
        )
        return tuple(name for name, stored, calculated in pairs if stored != calculated)


@dataclass(frozen=True, slots=True, kw_only=True)
class Invoice:
    """Factura completa (F1) emitida por la app.

    Campos de la AEAT que la v1 fija: ``invoice_type`` F1 (las rectificativas
    son ``CorrectiveInvoice``) y ``regime_key`` 01. La calificación (S1 o S2)
    va en ``treatment``.

    ``recipient_type`` y ``dwelling_over_two_years`` solo se guardan si la
    factura no sale de un presupuesto (RN-F-13); si sale, se leen de la versión
    del presupuesto.

    ``gross_amount`` es el importe con IVA incluido del anticipo (RN-F-12): con
    él, la base sale del importe y no de las líneas.

    ``issued_amounts`` solo lo pasa el repositorio al leer una factura emitida:
    con él se comprueban la estructura y que los importes guardados cuadran,
    pero no las reglas de emisión, que pueden haber cambiado desde que se
    emitió (RN-F-02). Sin él, la factura se valida entera con las reglas
    vigentes; así se crea y se edita el borrador, y así lo valida ``issue``.
    """

    id: InvoiceId
    tenant_id: TenantId
    customer_id: CustomerId
    series: Series
    treatment: VatTreatment
    lines: tuple[LineItem, ...]
    created_at: datetime
    description: str | None = None
    invoice_type: InvoiceType = InvoiceType.F1
    regime_key: RegimeKey = RegimeKey.GENERAL
    phase_type: PhaseType | None = PhaseType.FULL
    quote_version_id: QuoteVersionId | None = None
    recipient_type: RecipientType | None = None
    dwelling_over_two_years: bool | None = None
    gross_amount: Money | None = None
    withholding_rate: Percentage | None = None
    guarantee: Guarantee | None = None
    operation_date: date | None = None
    due_date: date | None = None
    status: InvoiceStatus = InvoiceStatus.DRAFT
    number: DocumentNumber | None = None
    issue_date: date | None = None
    issued_at: datetime | None = None
    issuer: Party | None = None
    recipient: Party | None = None
    # InitVar y no campo: lo guardado solo sirve para comprobar la lectura. Si
    # fuera un campo, ``replace`` lo arrastraría y la factura tendría dos
    # fuentes de importes que podrían discrepar.
    issued_amounts: InitVar[IssuedAmounts | None] = None

    def __post_init__(self, issued_amounts: IssuedAmounts | None) -> None:
        _check_structure(self)
        self._check_kind()
        _check_status(self)
        _check_amounts(self)
        if issued_amounts is None:
            self._check_issue_rules()
        else:
            _check_reconstituted(self, issued_amounts)

    @property
    def totals(self) -> InvoiceTotals:
        if self.gross_amount is not None:
            return totals_from_gross(self.gross_amount, self.treatment, self.withholding_rate)
        guarantee_rate = None if self.guarantee is None else self.guarantee.rate
        return totals_from_lines(
            (line.base for line in self.lines),
            self.treatment,
            self.withholding_rate,
            guarantee_rate,
        )

    @property
    def is_issued(self) -> bool:
        return self.status is InvoiceStatus.ISSUED

    @property
    def additional_work(self) -> tuple[LineItem, ...]:
        """Trabajo adicional (RF-FA-12): se marca en la app, no en la factura."""
        return tuple(line for line in self.lines if line.is_additional_work)

    # Edición del borrador: cada cambio devuelve otra factura y vuelve a validarla.

    def with_lines(self, lines: Iterable[LineItem]) -> Self:
        self._ensure_draft()
        return replace(self, lines=tuple(lines))

    def add_line(self, line: LineItem) -> Self:
        self._ensure_draft()
        return replace(self, lines=(*self.lines, line))

    def with_description(self, description: str | None) -> Self:
        self._ensure_draft()
        return replace(self, description=description)

    def with_treatment(self, treatment: VatTreatment) -> Self:
        self._ensure_draft()
        return replace(self, treatment=treatment)

    def with_withholding(self, rate: Percentage | None) -> Self:
        self._ensure_draft()
        return replace(self, withholding_rate=rate)

    def with_guarantee(self, guarantee: Guarantee | None) -> Self:
        self._ensure_draft()
        return replace(self, guarantee=guarantee)

    def with_dates(self, *, operation_date: date | None, due_date: date | None) -> Self:
        self._ensure_draft()
        return replace(self, operation_date=operation_date, due_date=due_date)

    def missing_issue_data(self) -> tuple[str, ...]:
        """Datos de la propia factura que faltan para emitir (RN-F-06).

        El NIF del destinatario y del emisor los garantiza ``Party``; sus
        domicilios los comprueba ``issue``, que recibe las partes. La pantalla
        de confirmación usa esta lista antes de emitir.
        """
        missing: list[str] = []
        if self.description is None:
            missing.append("description")
        if not self.lines:
            missing.append("lines")
        if self.quote_version_id is None and self.recipient_type is None:
            missing.append("recipient_type")
        if (
            self.quote_version_id is None
            and self.recipient_type in _REDUCED_ELIGIBLE
            and self.dwelling_over_two_years is None
        ):
            missing.append("dwelling_over_two_years")
        return tuple(missing)

    def issue(
        self,
        *,
        number: DocumentNumber,
        issue_date: date,
        issued_at: datetime,
        issuer: Party,
        recipient: Party,
        last_issue_date: date | None,
    ) -> Self:
        """Emite el borrador con el número que da el contador ya bloqueado (RN-F-01).

        Comprueba los datos obligatorios (RN-F-06), domicilios de las dos partes
        incluidos, y la fecha frente a la última de la serie (RN-F-04).
        ``issued_at`` sale del ``Clock``, en el caso de uso.
        """
        self._ensure_draft()
        missing = list(self.missing_issue_data())
        if issuer.address is None:
            missing.append("issuer_address")
        if recipient.address is None:
            missing.append("recipient_address")
        if missing:
            raise MissingIssueDataError(missing)
        if number.series != self.series or number.year != issue_date.year:
            raise InvalidDocumentNumberError("El número no es de la serie y el año de la factura.")
        check_issue_date(issue_date, last_issue_date)
        if self._forbids_negative_base() and self.totals.base.is_negative():
            msg = "La base no puede ser negativa: lo facturado de más se rectifica."
            raise NegativeInvoiceBaseError(msg)
        return replace(
            self,
            status=InvoiceStatus.ISSUED,
            number=number,
            issue_date=issue_date,
            issued_at=issued_at,
            issuer=issuer,
            recipient=recipient,
        )

    def _ensure_draft(self) -> None:
        if self.is_issued:
            msg = "Una factura emitida no se modifica; se corrige con una rectificativa."
            raise InvoiceAlreadyIssuedError(msg)

    def _forbids_negative_base(self) -> bool:
        # Una factura nunca resta: lo facturado de más se corrige con una
        # rectificativa por diferencias, que sí puede ser negativa (RN-F-12).
        return True

    def _check_kind(self) -> None:
        if self.invoice_type is not InvoiceType.F1:
            raise InvalidInvoiceError("Una factura de la v1 es completa (F1).")
        if self.phase_type is None:
            raise InvalidInvoiceError("Una factura lleva su fase (completa si no hay fases).")
        if self.phase_type is not PhaseType.FULL and self.quote_version_id is None:
            raise InvalidInvoiceError("Solo se factura por fases un presupuesto (RF-FA-10).")
        if (self.phase_type is PhaseType.ADVANCE) != (self.gross_amount is not None):
            msg = "El anticipo, y solo él, se factura por el importe cobrado (RN-F-12)."
            raise InvalidInvoiceError(msg)
        if self.phase_type is PhaseType.ADVANCE:
            _check_advance(self)
        if self.phase_type is not PhaseType.FINAL and any(
            line.origin is LineOrigin.PRIOR_INVOICE for line in self.lines
        ):
            raise InvalidInvoiceError("Solo la fase final resta facturas anteriores (RN-F-12).")

    def _check_issue_rules(self) -> None:
        _check_common_issue_rules(self)
        if self.guarantee is not None and self.phase_type not in _GUARANTEE_PHASES:
            msg = "La garantía solo cabe en la factura completa o en la fase final (RF-FA-15)."
            raise InvalidInvoiceError(msg)
        if self.phase_type in _WHOLE_WORKS_PHASES:
            _check_material_limit(self)

    @classmethod
    def advance(
        cls,
        *,
        id: InvoiceId,  # noqa: A002
        tenant_id: TenantId,
        customer_id: CustomerId,
        quote_version_id: QuoteVersionId,
        series: Series,
        treatment: VatTreatment,
        gross_amount: Money,
        line_description: str,
        created_at: datetime,
        description: str | None = None,
        withholding_rate: Percentage | None = None,
    ) -> Self:
        """Borrador de anticipo por el importe cobrado, con IVA incluido (RN-F-12).

        Lleva una sola línea por la base calculada a partir del importe, con
        el tipo de la obra (RN-F-13). No admite garantía (RF-FA-15).
        """
        base = totals_from_gross(gross_amount, treatment).base
        line = LineItem(description=line_description, quantity=Quantity.one(), unit_price=base)
        return cls(
            id=id,
            tenant_id=tenant_id,
            customer_id=customer_id,
            series=series,
            treatment=treatment,
            lines=(line,),
            created_at=created_at,
            description=description,
            phase_type=PhaseType.ADVANCE,
            quote_version_id=quote_version_id,
            gross_amount=gross_amount,
            withholding_rate=withholding_rate,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RectifiedInvoice:
    """Factura que rectifica una rectificativa (``invoice_corrections``, RN-F-03).

    En la rectificativa por sustitución guarda la base y la cuota rectificadas
    (las de la factura original); en la de diferencias, ninguna.
    """

    invoice_id: InvoiceId
    number: DocumentNumber
    issue_date: date
    rectified_base: Money | None = None
    rectified_tax: Money | None = None

    def __post_init__(self) -> None:
        if (self.rectified_base is None) != (self.rectified_tax is None):
            raise InvalidInvoiceError("La base y la cuota rectificadas van juntas.")


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectiveInvoice(Invoice):
    """Factura rectificativa (RF-FA-04, RN-F-03).

    Rectifica una o varias facturas, indica el motivo y guarda su clase (R1 a
    R4) y si es por sustitución o por diferencias. Por diferencias, sus líneas
    son la diferencia y la base puede ser negativa. Por sustitución, sus líneas
    son el contenido correcto y guarda además la base y la cuota rectificadas.
    """

    # Se redefinen sin el valor por defecto de Invoice: una rectificativa
    # declara siempre su clase y no es una fase de facturación.
    invoice_type: InvoiceType
    phase_type: PhaseType | None = None
    correction_type: CorrectionType
    rectified: tuple[RectifiedInvoice, ...]
    reason: str

    def _forbids_negative_base(self) -> bool:
        return self.correction_type is CorrectionType.SUBSTITUTION

    def _check_kind(self) -> None:
        if not self.invoice_type.is_corrective:
            raise InvalidInvoiceError("Una rectificativa de la v1 es de clase R1 a R4.")
        if self.phase_type is not None or self.gross_amount is not None:
            raise InvalidInvoiceError("Una rectificativa no es una fase de facturación.")
        if not self.reason.strip():
            msg = f"El motivo es obligatorio y admite {MAX_DESCRIPTION_LENGTH} caracteres."
            raise InvalidInvoiceError(msg)
        if not self.rectified:
            raise InvalidInvoiceError("Una rectificativa cita al menos una factura (RN-F-03).")
        ids = [item.invoice_id for item in self.rectified]
        if len(set(ids)) != len(ids):
            raise InvalidInvoiceError("Una factura no se cita dos veces en la misma rectificativa.")
        substitution = self.correction_type is CorrectionType.SUBSTITUTION
        if any((item.rectified_base is not None) != substitution for item in self.rectified):
            msg = "Solo la rectificativa por sustitución, y siempre, guarda lo rectificado."
            raise InvalidInvoiceError(msg)

    def _check_issue_rules(self) -> None:
        _check_common_issue_rules(self)
        # R5 es de facturas simplificadas, que la v1 no emite.
        if not self.invoice_type.is_supported:
            raise InvalidInvoiceError("Una rectificativa de la v1 es de clase R1 a R4.")
        if self.guarantee is not None:
            raise InvalidInvoiceError("Una rectificativa no lleva garantía.")
        if len(self.reason) > MAX_DESCRIPTION_LENGTH:
            msg = f"El motivo es obligatorio y admite {MAX_DESCRIPTION_LENGTH} caracteres."
            raise InvalidInvoiceError(msg)

    @property
    def rectified_base_total(self) -> Money | None:
        """Suma de bases rectificadas (BaseRectificada), solo por sustitución."""
        return _sum_optional(item.rectified_base for item in self.rectified)

    @property
    def rectified_tax_total(self) -> Money | None:
        return _sum_optional(item.rectified_tax for item in self.rectified)


def _sum_optional(amounts: Iterable[Money | None]) -> Money | None:
    total: Money | None = None
    for amount in amounts:
        if amount is None:
            return None
        total = amount if total is None else total + amount
    return total


def _check_structure(invoice: Invoice) -> None:
    if invoice.created_at.tzinfo is None:
        raise InvalidInvoiceError("La fecha de creación debe llevar zona horaria.")
    if invoice.withholding_rate is not None and (
        invoice.withholding_rate.is_zero() or invoice.withholding_rate.value >= 100  # noqa: PLR2004
    ):
        raise InvalidInvoiceError("La retención es un porcentaje mayor que 0 y menor que 100.")
    if invoice.quote_version_id is None and any(line.origin is not None for line in invoice.lines):
        msg = "Sin presupuesto no hay líneas presupuestadas, adicionales ni restas de fases."
        raise InvalidInvoiceError(msg)
    if invoice.quote_version_id is not None and (
        invoice.recipient_type is not None or invoice.dwelling_over_two_years is not None
    ):
        msg = "Si la factura sale de un presupuesto, el destinatario y la vivienda están en él."
        raise InvalidInvoiceError(msg)


def _check_common_issue_rules(invoice: Invoice) -> None:
    """Reglas de emisión comunes a facturas y rectificativas (RN-F-06, RN-F-13)."""
    if invoice.description is not None and (
        not invoice.description.strip()
        or invoice.description != invoice.description.strip()
        or len(invoice.description) > MAX_DESCRIPTION_LENGTH
    ):
        msg = f"La descripción general es texto sin bordes en blanco de {MAX_DESCRIPTION_LENGTH}."
        raise InvalidInvoiceError(msg)
    _check_treatment(invoice)


def _check_reconstituted(invoice: Invoice, issued_amounts: IssuedAmounts) -> None:
    # Un borrador se puede seguir editando, así que se le aplican siempre las
    # reglas vigentes; solo lo emitido queda fijado tal como se emitió.
    if not invoice.is_issued:
        msg = "Solo una factura emitida se lee con sus importes guardados."
        raise InvalidInvoiceError(msg)
    differences = issued_amounts.differences(invoice.totals)
    if differences:
        msg = "Los importes guardados no cuadran con las líneas: " + ", ".join(differences)
        raise IssuedAmountsMismatchError(msg)


def _check_treatment(invoice: Invoice) -> None:
    general = VatTreatment.taxed(TaxRate.general())
    if any(line.outside_works for line in invoice.lines) and invoice.treatment != general:
        msg = "Lo que no forma parte de la obra va al 21 % en su propia factura (RN-F-13)."
        raise InvalidInvoiceError(msg)
    if invoice.recipient_type is None:
        return
    if invoice.treatment.is_reverse_charge and invoice.recipient_type is not RecipientType.BUSINESS:
        msg = "La inversión del sujeto pasivo solo cabe con un empresario como destinatario."
        raise InvalidInvoiceError(msg)
    if invoice.treatment.rate == TaxRate.reduced() and (
        invoice.recipient_type not in _REDUCED_ELIGIBLE or invoice.dwelling_over_two_years is False
    ):
        msg = "El 10 % exige un particular o una comunidad y una vivienda de más de dos años."
        raise InvalidInvoiceError(msg)


def _check_amounts(invoice: Invoice) -> None:
    # Calcula todos los importes al crear o editar el borrador: si alguno pasa
    # del máximo de Money (ADR-009), InvalidAmountError salta aquí y no al
    # leer ``totals`` en la emisión, en el PDF o al guardar.
    totals = invoice.totals
    _ = (totals.total_amount, totals.collectible, totals.amount_due)


def _check_material_limit(invoice: Invoice) -> None:
    if invoice.treatment.rate != TaxRate.reduced():
        return
    if material_share(invoice.lines).exceeds_limit:
        msg = "Con más del 40 % de material, la obra va al 21 % (RN-F-13)."
        raise InvalidInvoiceError(msg)


def _check_advance(invoice: Invoice) -> None:
    gross = invoice.gross_amount
    # _check_kind solo llama aquí si hay importe cobrado.
    if gross is None or not gross.is_positive():
        raise InvalidInvoiceError("El anticipo es un importe cobrado mayor que cero.")
    if len(invoice.lines) != 1:
        raise InvalidInvoiceError("El anticipo lleva una sola línea.")
    (line,) = invoice.lines
    expected_base = totals_from_gross(gross, invoice.treatment).base
    if (
        line.is_material
        or line.outside_works
        or line.origin is not None
        or line.base != expected_base
    ):
        msg = "La línea del anticipo es su base, calculada a partir del importe cobrado."
        raise InvalidInvoiceError(msg)


def _check_status(invoice: Invoice) -> None:
    if invoice.status is InvoiceStatus.DRAFT:
        issued_fields = (
            invoice.number,
            invoice.issue_date,
            invoice.issued_at,
            invoice.issuer,
            invoice.recipient,
        )
        if any(value is not None for value in issued_fields):
            raise InvalidInvoiceError("Un borrador no tiene número, fecha de emisión ni partes.")
        return
    number, issue_date, issued_at = invoice.number, invoice.issue_date, invoice.issued_at
    if (
        number is None
        or issue_date is None
        or issued_at is None
        or invoice.issuer is None
        or invoice.recipient is None
        or invoice.issuer.address is None
        or invoice.recipient.address is None
    ):
        msg = "Una emitida tiene número, fechas, y emisor y destinatario con domicilio."
        raise InvalidInvoiceError(msg)
    if issued_at.tzinfo is None:
        raise InvalidInvoiceError("La hora de emisión debe llevar zona horaria.")
    if number.series != invoice.series:
        raise InvalidDocumentNumberError("El número no es de la serie de la factura.")
    _check_after_issue_date(invoice, issue_date)


def _check_after_issue_date(invoice: Invoice, issue_date: date) -> None:
    if invoice.due_date is not None and invoice.due_date < issue_date:
        raise InvalidInvoiceError("El vencimiento no puede ser anterior a la expedición.")
    if invoice.guarantee is not None and invoice.guarantee.due_date < issue_date:
        msg = "El vencimiento de la garantía no puede ser anterior a la expedición."
        raise InvalidInvoiceError(msg)
