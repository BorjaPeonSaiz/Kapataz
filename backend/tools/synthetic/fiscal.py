"""Reglas fiscales del generador, todas en este módulo.

El tipo de IVA de la obra lo decide el dominio (``works_vat``, RN-F-13). Lo
que el dominio aún no decide, porque solo aparece en el histórico importado, se
fija aquí de forma **provisional** y está pendiente de la lista del asesor:

1. Inversión del sujeto pasivo (art. 84.Uno.2.º f de la Ley 37/1992): solo en
   las obras del albañil para constructoras y promotoras (``is_contractor``).
   La obra para una empresa que no construye (una clínica que reforma su
   local) va al 21 % sin inversión.
2. Retención de IRPF del 1 % (art. 95.6 del RIRPF, estimación objetiva): solo
   el albañil, y solo en las facturas a empresas. El electricista está en
   estimación directa y no lleva retención.
3. Retención de garantía del 5 % de la base en las certificaciones de algunas
   obras para constructoras. El dominio solo la admite en la factura completa o
   en la fase final (RF-FA-15); en el histórico va en cada certificación, como
   es habitual en la subcontratación.
4. Lo que se vende fuera de la obra (``outside_works``) va al 21 % en la misma
   factura, con desglose por tipos, como haría otro programa. La app lo
   separaría en otra factura (``split_by_vat``).
"""

from collections.abc import Iterable
from decimal import Decimal

from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import REVERSE_CHARGE_MENTION, TaxRate
from kapataz.domain.billing.works_vat import (
    decide_works_vat,
    material_share,
    recipient_obstacles,
)
from synthetic.model import LineData, Trade

GENERAL_RATE = Decimal(21)
REDUCED_RATE = Decimal(10)
BRICKLAYER_WITHHOLDING_RATE = Decimal(1)
GUARANTEE_RATE = Decimal(5)

REVERSE_CHARGE_TEXT = (
    f"{REVERSE_CHARGE_MENTION}. Operación sujeta conforme al art. 84.Uno.2.º f) "
    "de la Ley 37/1992 del IVA; el destinatario liquida el impuesto."
)


def applies_reverse_charge(trade: Trade, *, is_contractor: bool) -> bool:
    """Regla provisional 1."""
    return trade is Trade.BRICKLAYER and is_contractor


def withholding_rate(trade: Trade, recipient_type: RecipientType) -> Decimal | None:
    """Regla provisional 2."""
    if trade is Trade.BRICKLAYER and recipient_type is RecipientType.BUSINESS:
        return BRICKLAYER_WITHHOLDING_RATE
    return None


def works_rate(
    lines: Iterable[LineData],
    recipient_type: RecipientType,
    *,
    dwelling_over_two_years: bool | None,
) -> Decimal:
    """Tipo de la obra entera con la regla del dominio (RN-F-13, regla del 40 %)."""
    items = [
        LineItem(
            description=line.description,
            quantity=Quantity(line.quantity),
            unit_price=Money(line.unit_price),
            discount=None if line.discount is None else Percentage(line.discount),
            is_material=line.is_material,
            outside_works=line.outside_works,
        )
        for line in lines
    ]
    if dwelling_over_two_years is None:
        # Sin dato de vivienda solo puede ir una empresa, y el destinatario ya basta para
        # que la obra no vaya al reducido. A un particular o a una comunidad se le pregunta.
        if not recipient_obstacles(recipient_type, None):
            msg = "A un particular o a una comunidad hay que decirle si la vivienda tiene dos años."
            raise ValueError(msg)
        return TaxRate.general().percent
    decision = decide_works_vat(recipient_type, dwelling_over_two_years, material_share(items))
    return decision.rate.percent


def line_rate(
    *,
    outside_works: bool,
    works: Decimal,
    reverse_charge: bool,
) -> Decimal | None:
    """Tipo de una línea: ninguno con inversión; el general fuera de la obra (regla 4)."""
    if reverse_charge:
        return None
    return GENERAL_RATE if outside_works else works
