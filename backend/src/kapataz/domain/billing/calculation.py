"""Cálculo de importes: funciones puras sobre Money (RN-01 a RN-03, RN-F-05, RN-F-12).

Es el único sitio del sistema que calcula bases, cuotas, retenciones y totales
(ADR-009). El LLM nunca calcula importes (RN-02): si propone un total, se
descarta y se recalcula aquí.

Reglas de redondeo (RN-03):

- La base de cada línea se redondea a céntimos una vez.
- La base de la factura es la suma exacta de las bases de sus líneas.
- La cuota se redondea una vez sobre la base de la factura (una factura lleva
  un solo tipo, RN-F-13, así que hay una sola cuota).
- Total = base + cuota, sin redondeo adicional.
- Excepción: si se parte de un importe con IVA incluido (el anticipo cobrado,
  RN-F-12), se redondea la base y la cuota es la diferencia, para que el total
  coincida al céntimo con lo cobrado.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from kapataz.domain.billing.errors import InvalidAmountError
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import VatTreatment


def line_base(quantity: Quantity, unit_price: Money, discount: Percentage | None = None) -> Money:
    """Base de una línea: cantidad × precio × (1 − descuento), redondeada una vez."""
    exact = quantity.as_fraction() * unit_price.as_fraction()
    if discount is not None:
        exact *= 1 - discount.as_fraction()
    return Money.round(exact)


@dataclass(frozen=True, slots=True)
class TaxBreakdown:
    """Desglose de una factura: un tratamiento, una base y una cuota.

    Coincide con un ``DetalleDesglose`` del registro de la AEAT. Se construye
    con ``tax_breakdown`` o ``tax_breakdown_from_gross``, que garantizan que la
    cuota sale de la base con las reglas de RN-03.
    """

    treatment: VatTreatment
    base: Money
    tax: Money

    def __post_init__(self) -> None:
        if self.treatment.is_reverse_charge and not self.tax.is_zero():
            raise InvalidAmountError("Con inversión del sujeto pasivo la cuota es cero.")

    @property
    def total(self) -> Money:
        return self.base + self.tax


def tax_breakdown(base: Money, treatment: VatTreatment) -> TaxBreakdown:
    """Cuota sobre la base: base × tipo, redondeada una vez (RN-03).

    Con inversión del sujeto pasivo la cuota es cero (RN-F-05).
    """
    tax = Money.round(base.as_fraction() * treatment.effective_rate)
    return TaxBreakdown(treatment, base, tax)


def tax_breakdown_from_gross(gross: Money, treatment: VatTreatment) -> TaxBreakdown:
    """Desglose de un importe con IVA incluido (excepción de RN-03, RN-F-12).

    Base = importe / (1 + tipo), redondeada; cuota = importe − base. Con 6.000 €
    al 10 %: base 5.454,55 € y cuota 545,45 €. El total coincide siempre al
    céntimo con el importe de partida.
    """
    base = Money.round(gross.as_fraction() / (1 + treatment.effective_rate))
    return TaxBreakdown(treatment, base, gross - base)


@dataclass(frozen=True, slots=True)
class InvoiceTotals:
    """Importes de una factura.

    - ``total_amount``: base + cuota (ImporteTotal del registro de la AEAT). No
      resta la retención de IRPF ni la garantía.
    - ``withholding``: retención de IRPF sobre la base (``Withholding``).
    - ``guarantee``: parte de la base cuyo cobro se aplaza (``Guarantee``,
      RF-FA-15). No cambia la base ni la cuota: solo aplaza el cobro.
    - ``amount_due``: lo que se cobra ahora: total − retención − garantía.
    - ``collectible``: lo que el cliente paga en total, ahora y al vencer la
      garantía: total − retención. Es el tope de los cobros (RN-F-10).
    """

    breakdown: TaxBreakdown
    withholding: Money
    guarantee: Money

    @property
    def base(self) -> Money:
        return self.breakdown.base

    @property
    def tax(self) -> Money:
        return self.breakdown.tax

    @property
    def total_amount(self) -> Money:
        return self.breakdown.total

    @property
    def collectible(self) -> Money:
        return self.total_amount - self.withholding

    @property
    def amount_due(self) -> Money:
        return self.collectible - self.guarantee


def invoice_totals(
    breakdown: TaxBreakdown,
    withholding_rate: Percentage | None = None,
    guarantee_rate: Percentage | None = None,
) -> InvoiceTotals:
    """Retención y garantía sobre la base del desglose, redondeadas una vez cada una."""
    return InvoiceTotals(
        breakdown=breakdown,
        withholding=_share_of(breakdown.base, withholding_rate),
        guarantee=_share_of(breakdown.base, guarantee_rate),
    )


def totals_from_lines(
    line_bases: Iterable[Money],
    treatment: VatTreatment,
    withholding_rate: Percentage | None = None,
    guarantee_rate: Percentage | None = None,
) -> InvoiceTotals:
    """Totales de una factura a partir de las bases ya redondeadas de sus líneas."""
    breakdown = tax_breakdown(sum_money(line_bases), treatment)
    return invoice_totals(breakdown, withholding_rate, guarantee_rate)


def totals_from_gross(
    gross: Money,
    treatment: VatTreatment,
    withholding_rate: Percentage | None = None,
) -> InvoiceTotals:
    """Totales de una factura que parte de un importe con IVA incluido (anticipo).

    ``gross`` es el importe del anticipo con IVA incluido. Con retención de
    IRPF, el cliente ingresa ``amount_due`` y la retención la paga a Hacienda
    por cuenta del profesional. No admite garantía (RF-FA-15).
    """
    return invoice_totals(tax_breakdown_from_gross(gross, treatment), withholding_rate)


def _share_of(base: Money, rate: Percentage | None) -> Money:
    if rate is None:
        return Money.zero()
    return Money.round(base.as_fraction() * rate.as_fraction())
