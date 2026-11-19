"""Cálculo de importes: líneas, cuota, anticipo, retención y garantía (RN-01 a RN-03, RN-F-05)."""

from decimal import Decimal

import pytest

from kapataz.domain.billing.calculation import (
    InvoiceTotals,
    TaxBreakdown,
    invoice_totals,
    line_base,
    tax_breakdown,
    tax_breakdown_from_gross,
    totals_from_gross,
    totals_from_lines,
)
from kapataz.domain.billing.errors import InvalidAmountError
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.unit.domain.billing_factories import GENERAL, REDUCED, money

SUPER_REDUCED = VatTreatment.taxed(TaxRate.super_reduced())
REVERSE = VatTreatment.reverse_charge()


@pytest.mark.req("RN-03")
@pytest.mark.parametrize(
    ("quantity", "price", "discount", "expected"),
    [
        ("3", "45.00", None, "135.00"),
        ("2.125", "12.35", None, "26.24"),  # 26,24375
        ("1", "10.00", "15", "8.50"),
        ("3", "0.35", "10", "0.95"),  # 0,945 sube
        ("0.001", "0.01", None, "0.00"),
        ("1", "-45.00", None, "-45.00"),
        ("1", "100.00", "100", "0.00"),
    ],
)
def test_base_de_linea_redondeada_una_vez(quantity, price, discount, expected):
    pct = None if discount is None else Percentage.of(discount)
    assert line_base(Quantity.of(quantity), money(price), pct) == money(expected)


@pytest.mark.req("RN-03")
def test_la_cuota_se_redondea_sobre_la_base_de_la_factura():
    # Diez líneas de 0,07 € al 21 %: redondear la cuota de cada línea daría
    # 10 × 0,01 = 0,10 €; la cuota de la base (0,70 €) es 0,147, que da 0,15 €.
    totals = totals_from_lines([money("0.07")] * 10, GENERAL)
    assert totals.base == money("0.70")
    assert totals.tax == money("0.15")
    assert totals.total_amount == money("0.85")


@pytest.mark.req("RN-03")
@pytest.mark.parametrize(
    ("treatment", "base", "tax"),
    [
        (GENERAL, "10000.00", "2100.00"),
        (REDUCED, "8000.00", "800.00"),
        (SUPER_REDUCED, "12.13", "0.49"),  # 0,4852
        (GENERAL, "0.02", "0.00"),  # 0,0042
        (GENERAL, "-1000.00", "-210.00"),
        (GENERAL, "-0.10", "-0.02"),  # -0,021
    ],
)
def test_cuota_por_tipo(treatment, base, tax):
    breakdown = tax_breakdown(money(base), treatment)
    assert breakdown.tax == money(tax)
    assert breakdown.total == money(base) + money(tax)


@pytest.mark.req("RN-F-05")
def test_inversion_del_sujeto_pasivo_lleva_cuota_cero():
    totals = totals_from_lines([money("5000.00")], REVERSE)
    assert totals.tax == money("0.00")
    assert totals.total_amount == money("5000.00")


@pytest.mark.req("RN-F-05")
def test_un_desglose_con_inversion_y_cuota_es_imposible():
    with pytest.raises(InvalidAmountError):
        TaxBreakdown(REVERSE, money("100.00"), money("21.00"))


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-03")
def test_anticipo_de_6000_al_10():
    breakdown = tax_breakdown_from_gross(money("6000.00"), REDUCED)
    assert breakdown.base == money("5454.55")
    assert breakdown.tax == money("545.45")
    assert breakdown.total == money("6000.00")


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-03")
def test_anticipo_de_3630_al_21():
    breakdown = tax_breakdown_from_gross(money("3630.00"), GENERAL)
    assert (breakdown.base, breakdown.tax) == (money("3000.00"), money("630.00"))


@pytest.mark.req("RN-03")
@pytest.mark.parametrize("gross", ["0.01", "0.05", "1.00", "99.99", "1234.56", "21474836.47"])
@pytest.mark.parametrize("treatment", [GENERAL, REDUCED, SUPER_REDUCED, REVERSE])
def test_desde_importe_con_iva_el_total_coincide_al_centimo(gross, treatment):
    breakdown = tax_breakdown_from_gross(money(gross), treatment)
    assert breakdown.total == money(gross)


@pytest.mark.req("RN-03")
def test_anticipo_con_inversion_no_tiene_cuota():
    breakdown = tax_breakdown_from_gross(money("5000.00"), REVERSE)
    assert (breakdown.base, breakdown.tax) == (money("5000.00"), money("0.00"))


@pytest.mark.req("RF-FA-15")
@pytest.mark.req("RN-F-10")
def test_garantia_del_5_en_la_final():
    totals = totals_from_lines([money("10000.00")], GENERAL, guarantee_rate=Percentage.of("5"))
    assert totals.total_amount == money("12100.00")
    assert totals.guarantee == money("500.00")
    assert totals.amount_due == money("11600.00")
    assert totals.collectible == money("12100.00")


@pytest.mark.req("RF-FA-05")
@pytest.mark.req("RN-F-10")
def test_retencion_de_irpf_no_resta_del_total():
    totals = totals_from_lines(
        [money("1000.00")],
        GENERAL,
        withholding_rate=Percentage.of("15"),
        guarantee_rate=Percentage.of("10"),
    )
    assert totals.total_amount == money("1210.00")
    assert totals.withholding == money("150.00")
    assert totals.collectible == money("1060.00")
    assert totals.amount_due == money("960.00")


@pytest.mark.req("RN-F-12")
def test_anticipo_con_retencion():
    totals = totals_from_gross(money("1210.00"), GENERAL, withholding_rate=Percentage.of("15"))
    assert totals.base == money("1000.00")
    assert totals.withholding == money("150.00")
    assert totals.guarantee == money("0.00")
    assert totals.amount_due == money("1060.00")


@pytest.mark.req("RN-03")
def test_retencion_redondeada_sobre_la_base():
    breakdown = tax_breakdown(money("333.33"), GENERAL)
    totals = invoice_totals(breakdown, Percentage.of("7"))
    assert totals.withholding == money("23.33")  # 23,3331
    assert isinstance(totals, InvoiceTotals)
    assert totals.withholding.amount == Decimal("23.33")
