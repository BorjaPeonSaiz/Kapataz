"""Objeto de valor LineItem: una línea con precio de una factura."""

from dataclasses import dataclass

from kapataz.domain.billing.calculation import line_base
from kapataz.domain.billing.codes import LineOrigin
from kapataz.domain.billing.errors import InvalidLineItemError
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.quantity import Percentage, Quantity

MAX_LINE_DESCRIPTION_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class LineItem:
    """Concepto concreto con cantidad y precio dentro de una factura.

    - ``is_material`` cuenta para el límite del 40 % de material (RN-F-13).
    - ``outside_works`` marca lo que no forma parte de la obra (muebles o
      electrodomésticos que solo se venden): va al 21 % en otra factura.
    - ``origin`` es None si la factura no sale de un presupuesto. Si sale,
      distingue lo presupuestado (``QUOTE``, con la línea del presupuesto en
      ``quote_line_id``), el trabajo adicional y la resta de una factura
      anterior en la fase final (``PRIOR_INVOICE``, RN-F-12).
    """

    description: str
    quantity: Quantity
    unit_price: Money
    discount: Percentage | None = None
    is_material: bool = False
    outside_works: bool = False
    origin: LineOrigin | None = None
    quote_line_id: QuoteLineId | None = None
    prior_invoice_id: InvoiceId | None = None

    def __post_init__(self) -> None:
        _check_description(self.description)
        if self.is_material and self.outside_works:
            msg = "Una línea fuera de la obra no puede ser material de la obra."
            raise InvalidLineItemError(msg)
        if (self.origin is LineOrigin.QUOTE) != (self.quote_line_id is not None):
            msg = "Solo una línea del presupuesto, y siempre, cita su línea de presupuesto."
            raise InvalidLineItemError(msg)
        if (self.origin is LineOrigin.PRIOR_INVOICE) != (self.prior_invoice_id is not None):
            msg = "Solo una línea que resta una factura anterior, y siempre, la cita."
            raise InvalidLineItemError(msg)
        if self.origin is LineOrigin.PRIOR_INVOICE:
            _check_prior_invoice_line(self)
        # Una base que pasa del máximo de Money se rechaza al crear la línea.
        _ = self.base

    @property
    def base(self) -> Money:
        return line_base(self.quantity, self.unit_price, self.discount)

    @property
    def priced_base(self) -> Money | None:
        """La base, que en una factura siempre existe (ver ``WorksLine``)."""
        return self.base

    @property
    def counts_for_works(self) -> bool:
        """Si la línea forma parte de la obra para calcular el 40 % (RN-F-13)."""
        return not self.outside_works and self.origin is not LineOrigin.PRIOR_INVOICE

    @property
    def is_additional_work(self) -> bool:
        return self.origin is LineOrigin.ADDITIONAL


def _check_description(description: str) -> None:
    if not description.strip() or description != description.strip():
        raise InvalidLineItemError("Una línea necesita una descripción sin espacios sobrantes.")
    if len(description) > MAX_LINE_DESCRIPTION_LENGTH:
        msg = f"La descripción de una línea admite {MAX_LINE_DESCRIPTION_LENGTH} caracteres."
        raise InvalidLineItemError(msg)


def _check_prior_invoice_line(line: LineItem) -> None:
    # Resta la base entera de una factura ya emitida: una unidad a precio
    # negativo, sin descuento ni marcas de obra que alteren el 40 %.
    if (
        line.quantity != Quantity.one()
        or line.unit_price.is_positive()
        or line.discount is not None
        or line.is_material
        or line.outside_works
    ):
        msg = "La resta de una factura anterior es una unidad a precio no positivo, sin más."
        raise InvalidLineItemError(msg)
