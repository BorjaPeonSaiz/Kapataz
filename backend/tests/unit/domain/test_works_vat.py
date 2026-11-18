"""Tipo de IVA de la obra, límite del 40 % y separación por tipos (RN-F-13)."""

from decimal import Decimal

import pytest

from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.errors import InvalidTaxRateError
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.domain.billing.works_vat import (
    MaterialShare,
    VatRateReason,
    decide_works_vat,
    material_share,
    split_by_vat,
    works_treatment,
)
from tests.unit.domain.billing_factories import GENERAL, REDUCED, line, money


def share(works: str, material: str) -> MaterialShare:
    return MaterialShare(money(works), money(material))


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize("recipient", [RecipientType.PRIVATE, RecipientType.COMMUNITY])
def test_reforma_de_vivienda_al_10(recipient):
    decision = decide_works_vat(recipient, True, share("5000.00", "1000.00"))
    assert decision.rate == TaxRate.reduced()
    assert decision.reasons == ()
    assert decision.is_reduced
    assert not decision.warn_material_near_limit


@pytest.mark.req("RN-F-13")
def test_el_material_supera_el_40_y_toda_la_obra_va_al_21():
    decision = decide_works_vat(RecipientType.PRIVATE, True, share("5000.00", "2500.00"))
    assert decision.rate == TaxRate.general()
    assert decision.reasons == (VatRateReason.MATERIAL_OVER_LIMIT,)
    assert decision.material.percent == Decimal("50.00")


@pytest.mark.req("RN-F-13")
def test_material_cerca_del_limite_avisa_y_mantiene_el_10():
    decision = decide_works_vat(RecipientType.PRIVATE, True, share("5000.00", "1800.00"))
    assert decision.rate == TaxRate.reduced()
    assert decision.warn_material_near_limit
    assert decision.material.percent == Decimal("36.00")


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    ("material", "near", "exceeds"),
    [
        ("3499.99", False, False),  # por debajo del 35 %
        ("3500.00", True, False),  # el 35 % justo ya avisa
        ("4000.00", True, False),  # el 40 % justo no supera el límite
        ("4000.01", False, True),
    ],
)
def test_umbrales_del_35_y_del_40(material, near, exceeds):
    material_share_ = share("10000.00", material)
    assert material_share_.near_limit is near
    assert material_share_.exceeds_limit is exceeds


@pytest.mark.req("RN-F-13")
def test_sin_base_positiva_no_hay_peso_del_material():
    empty = share("0.00", "0.00")
    assert empty.ratio is None
    assert empty.percent is None
    assert not empty.exceeds_limit
    assert not empty.near_limit


@pytest.mark.req("RN-F-13")
def test_porcentaje_de_material_redondeado_para_mostrar():
    assert share("3.00", "1.00").percent == Decimal("33.33")
    assert share("3.00", "2.00").percent == Decimal("66.67")
    assert share("100.00", "-1.00").percent == Decimal("-1.00")


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    ("recipient", "dwelling", "reasons"),
    [
        (RecipientType.BUSINESS, True, (VatRateReason.RECIPIENT_NOT_ELIGIBLE,)),
        (RecipientType.PRIVATE, False, (VatRateReason.DWELLING_TOO_RECENT,)),
        (
            RecipientType.BUSINESS,
            False,
            (VatRateReason.RECIPIENT_NOT_ELIGIBLE, VatRateReason.DWELLING_TOO_RECENT),
        ),
    ],
)
def test_motivos_para_el_21(recipient, dwelling, reasons):
    decision = decide_works_vat(recipient, dwelling, share("1000.00", "100.00"))
    assert decision.rate == TaxRate.general()
    assert decision.reasons == reasons
    assert not decision.warn_material_near_limit


@pytest.mark.req("RN-F-13")
def test_el_40_se_calcula_sin_lo_que_va_fuera_de_la_obra():
    lines = [
        line("3000.00"),
        line("1800.00", is_material=True),
        line("600.00", outside_works=True),
    ]
    result = material_share(lines)
    assert result.works_base == money("4800.00")
    assert result.material_base == money("1800.00")


@pytest.mark.req("RF-FA-05")
def test_inversion_del_sujeto_pasivo_solo_con_empresario():
    decision = decide_works_vat(RecipientType.BUSINESS, True, share("1000.00", "0.00"))
    treatment = works_treatment(decision, RecipientType.BUSINESS, reverse_charge=True)
    assert treatment == VatTreatment.reverse_charge()
    assert works_treatment(decision, RecipientType.BUSINESS, reverse_charge=False) == GENERAL
    private = decide_works_vat(RecipientType.PRIVATE, True, share("1000.00", "0.00"))
    with pytest.raises(InvalidTaxRateError):
        works_treatment(private, RecipientType.PRIVATE, reverse_charge=True)


@pytest.mark.req("RN-F-13")
def test_presupuesto_con_lineas_a_dos_tipos_genera_dos_facturas():
    works = line("8000.00")
    appliance = line("600.00", outside_works=True)
    groups = split_by_vat([works, appliance], REDUCED)
    assert [(group.treatment, group.lines) for group in groups] == [
        (REDUCED, (works,)),
        (GENERAL, (appliance,)),
    ]


@pytest.mark.req("RN-F-13")
def test_si_la_obra_ya_va_al_21_sale_una_sola_factura():
    works = line("8000.00")
    appliance = line("600.00", outside_works=True)
    groups = split_by_vat([works, appliance], GENERAL)
    assert len(groups) == 1
    assert groups[0].lines == (works, appliance)


@pytest.mark.req("RN-F-13")
def test_obra_con_inversion_y_venta_aparte():
    works = line("8000.00")
    appliance = line("600.00", outside_works=True)
    groups = split_by_vat([works, appliance], VatTreatment.reverse_charge())
    assert [group.treatment for group in groups] == [VatTreatment.reverse_charge(), GENERAL]


@pytest.mark.req("RN-F-13")
def test_sin_lineas_fuera_de_la_obra_no_hay_segunda_factura():
    groups = split_by_vat([line("100.00")], REDUCED)
    assert [group.treatment for group in groups] == [REDUCED]
