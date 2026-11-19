"""Objetos de valor de facturación: Money, Quantity, Percentage, TaxRate y VatTreatment."""

from decimal import Decimal
from fractions import Fraction

import pytest

from kapataz.domain.billing.errors import InvalidAmountError, InvalidTaxRateError
from kapataz.domain.billing.money import MAX_ABS_AMOUNT, Money, sum_money
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import (
    REVERSE_CHARGE_MENTION,
    OperationClass,
    TaxRate,
    VatTreatment,
)

# --------------------------------------------------------------------- Money


@pytest.mark.req("RN-01")
def test_money_rechaza_float():
    with pytest.raises(TypeError, match="RN-01"):
        Money(0.1)  # type: ignore[arg-type]


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", [1, "1.00", True])
def test_money_solo_admite_decimal(value):
    with pytest.raises(TypeError):
        Money(value)


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_money_rechaza_no_finitos(value):
    with pytest.raises(InvalidAmountError):
        Money(Decimal(value))


@pytest.mark.req("RN-01")
def test_money_rechaza_mas_de_dos_decimales_en_vez_de_redondear():
    with pytest.raises(InvalidAmountError):
        Money(Decimal("1.005"))


@pytest.mark.req("RN-01")
def test_money_normaliza_a_dos_decimales():
    assert str(Money(Decimal(10))) == "10.00"
    assert Money(Decimal(10)) == Money(Decimal("10.00"))
    assert str(Money(Decimal("-0.00"))) == "0.00"


@pytest.mark.req("RN-01")
def test_money_tiene_tope_del_integer_de_la_base_de_datos():
    assert Money(MAX_ABS_AMOUNT).amount == MAX_ABS_AMOUNT
    with pytest.raises(InvalidAmountError):
        Money(MAX_ABS_AMOUNT + Decimal("0.01"))
    with pytest.raises(InvalidAmountError):
        Money(-MAX_ABS_AMOUNT - Decimal("0.01"))


@pytest.mark.req("RN-03")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0.005"), "0.01"),
        (Decimal("0.0049"), "0.00"),
        (Decimal("-0.005"), "-0.01"),
        (Decimal("2.675"), "2.68"),
        (Fraction(6000, 1) / Fraction(110, 100), "5454.55"),
        (Fraction(1, 3), "0.33"),
        (Fraction(-2, 3), "-0.67"),
    ],
)
def test_redondeo_half_up_simetrico(value, expected):
    assert str(Money.round(value)) == expected


@pytest.mark.req("RN-01")
def test_redondeo_rechaza_decimal_no_finito():
    with pytest.raises(InvalidAmountError):
        Money.round(Decimal("NaN"))


@pytest.mark.req("RN-01")
def test_aritmetica_y_comparacion():
    a, b = Money.of("10.50"), Money.of("0.75")
    assert a + b == Money.of("11.25")
    assert a - b == Money.of("9.75")
    assert -a == Money.of("-10.50")
    assert abs(Money.of("-3.00")) == Money.of("3.00")
    assert b < a
    assert sorted([a, b]) == [b, a]
    assert Money.zero().is_zero()
    assert Money.of("-0.01").is_negative()
    assert Money.of("0.01").is_positive()
    assert a.as_fraction() == Fraction(21, 2)


@pytest.mark.req("RN-01")
def test_suma_de_importes():
    assert sum_money([]) == Money.zero()
    assert sum_money([Money.of("0.10"), Money.of("0.20")]) == Money.of("0.30")


# ------------------------------------------------------- Quantity y Percentage


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", ["1", "2.125", "999999.999", "0.001"])
def test_cantidades_validas(value):
    assert Quantity.of(value).value == Decimal(value)


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", ["0", "-1", "1.0001", "1000000", "NaN"])
def test_cantidades_no_validas(value):
    with pytest.raises(InvalidAmountError):
        Quantity(Decimal(value))


@pytest.mark.req("RN-01")
def test_cantidad_rechaza_float():
    with pytest.raises(TypeError):
        Quantity(1.5)  # type: ignore[arg-type]


@pytest.mark.req("RN-01")
def test_cantidad_unidad_y_texto():
    assert Quantity.one() == Quantity.of(1)
    assert str(Quantity.of("2.5")) == "2.5"
    assert Quantity.of("2.5").as_fraction() == Fraction(5, 2)


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", ["0", "15", "100", "12.50"])
def test_porcentajes_validos(value):
    pct = Percentage.of(value)
    assert pct.as_fraction() == Fraction(Decimal(value)) / 100
    assert str(pct) == value


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", ["-1", "100.01", "1.005", "Infinity"])
def test_porcentajes_no_validos(value):
    with pytest.raises(InvalidAmountError):
        Percentage(Decimal(value))


# ------------------------------------------------------------- TaxRate y trato


@pytest.mark.req("RF-FA-05")
@pytest.mark.parametrize(
    ("rate", "percent"),
    [(TaxRate.general(), "21"), (TaxRate.reduced(), "10"), (TaxRate.super_reduced(), "4")],
)
def test_tipos_de_iva_admitidos(rate, percent):
    assert str(rate) == percent
    assert TaxRate(Decimal(percent + ".00")) == rate


@pytest.mark.req("RF-FA-05")
@pytest.mark.parametrize("percent", ["18", "7", "0", "5", "NaN"])
def test_tipos_de_iva_no_vigentes(percent):
    with pytest.raises(InvalidTaxRateError):
        TaxRate(Decimal(percent))


@pytest.mark.req("RN-01")
def test_tipo_de_iva_rechaza_float():
    with pytest.raises(TypeError):
        TaxRate(21.0)  # type: ignore[arg-type]


@pytest.mark.req("RN-F-05")
def test_inversion_del_sujeto_pasivo_sin_tipo_y_con_mencion():
    treatment = VatTreatment.reverse_charge()
    assert treatment.is_reverse_charge
    assert treatment.effective_rate == 0
    assert treatment.mention == REVERSE_CHARGE_MENTION == "Inversión del sujeto pasivo"


@pytest.mark.req("RF-FA-05")
def test_operacion_sujeta_lleva_tipo_y_no_mencion():
    treatment = VatTreatment.taxed(TaxRate.general())
    assert treatment.operation_class is OperationClass.S1
    assert treatment.effective_rate == Fraction(21, 100)
    assert treatment.mention is None


@pytest.mark.req("RN-F-05")
@pytest.mark.parametrize(
    ("operation_class", "rate"),
    [
        (OperationClass.S1, None),
        (OperationClass.S2, TaxRate.general()),
        (OperationClass.N1, None),
        (OperationClass.N2, None),
    ],
)
def test_tratamientos_imposibles(operation_class, rate):
    with pytest.raises(InvalidTaxRateError):
        VatTreatment(operation_class, rate)


@pytest.mark.req("RF-FA-05")
def test_tipo_superreducido():
    assert TaxRate.super_reduced().percent == Decimal(4)
    assert TaxRate.super_reduced().as_fraction() == Fraction(4, 100)
