"""Facturación por fases y control de lo facturado (RN-F-11, RN-F-12, RN-F-13, ADR-033)."""

from datetime import date
from uuid import uuid4

import pytest

from kapataz.domain.billing.codes import CorrectionType, InvoiceType, LineOrigin, PhaseType
from kapataz.domain.billing.errors import InvalidPhaseError
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.phases import (
    FinalPhasePlan,
    OverbillingPlan,
    PriorPhase,
    billing_summary,
    check_against_pending,
    extra_vat_on_prior_phases,
    plan_final_phase,
    removed_works,
)
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.quote import PriceSource, QuoteLine
from kapataz.domain.billing.tax import VatTreatment
from tests.unit.domain.billing_factories import GENERAL, REDUCED, draft, line, money

QUOTE_VERSION = QuoteVersionId(uuid4())


def prior(
    base: str,
    tax: str,
    sequence: int,
    *,
    treatment: VatTreatment = GENERAL,
    phase: PhaseType = PhaseType.PROGRESS,
    issued: date | None = None,
) -> PriorPhase:
    return PriorPhase(
        invoice_id=InvoiceId(uuid4()),
        number=DocumentNumber.parse(f"F-2026-{sequence:04d}"),
        issue_date=issued or date(2026, 3, sequence),
        phase_type=phase,
        base=money(base),
        tax=money(tax),
        treatment=treatment,
    )


def realized(base: str, origin: LineOrigin = LineOrigin.QUOTE, **kwargs: object):
    return line(base, origin=origin, **kwargs)  # type: ignore[arg-type]


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RF-FA-10")
def test_fases_sin_cambios_sobre_el_presupuesto():
    advance = prior("3000.00", "630.00", 1, phase=PhaseType.ADVANCE)
    progress = prior("4000.00", "840.00", 2)
    plan = plan_final_phase(
        realized_lines=[realized("10000.00")],
        prior_phases=[progress, advance],
        treatment=GENERAL,
    )
    assert isinstance(plan, FinalPhasePlan)
    assert plan.service_base == money("10000.00")
    assert plan.prior_base == money("7000.00")
    assert plan.base == money("3000.00")
    assert plan.breakdown.tax == money("630.00")
    assert advance.base + progress.base + plan.base == money("10000.00")
    assert plan.extra_vat == ()
    # Las restas citan las fases en orden cronológico.
    deductions = [item for item in plan.lines if item.origin is LineOrigin.PRIOR_INVOICE]
    assert [d.prior_invoice_id for d in deductions] == [advance.invoice_id, progress.invoice_id]
    assert deductions[0].description == "A deducir: factura F-2026-0001 de 01/03/2026"
    assert deductions[0].base == money("-3000.00")


@pytest.mark.req("RN-F-12")
def test_la_final_sale_como_borrador_de_factura_final():
    plan = plan_final_phase(
        realized_lines=[realized("10000.00")],
        prior_phases=[prior("7000.00", "1470.00", 1)],
        treatment=GENERAL,
    )
    assert isinstance(plan, FinalPhasePlan)
    invoice = draft(
        *plan.lines,
        treatment=plan.treatment,
        phase_type=PhaseType.FINAL,
        quote_version_id=QUOTE_VERSION,
    )
    assert isinstance(invoice, Invoice)
    assert invoice.totals.base == money("3000.00")


@pytest.mark.req("RN-F-12")
def test_se_factura_menos_de_lo_presupuestado():
    plan = plan_final_phase(
        realized_lines=[realized("9000.00")],
        prior_phases=[prior("7000.00", "1470.00", 1)],
        treatment=GENERAL,
    )
    assert isinstance(plan, FinalPhasePlan)
    assert plan.base == money("2000.00")
    summary = billing_summary(money("10000.00"), [money("7000.00"), plan.base])
    assert summary.difference == money("-1000.00")
    assert summary.pending == money("1000.00")


@pytest.mark.req("RN-F-12")
def test_final_con_base_cero_cuando_ya_esta_todo_facturado():
    plan = plan_final_phase(
        realized_lines=[realized("7000.00")],
        prior_phases=[prior("7000.00", "1470.00", 1)],
        treatment=GENERAL,
    )
    assert isinstance(plan, FinalPhasePlan)
    assert plan.base == money("0.00")


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-F-03")
def test_se_ha_facturado_mas_de_lo_que_se_ha_hecho():
    floor = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Solado",
        quantity=Quantity.one(),
        unit_price=money("6000.00"),
        price_source=PriceSource.manual(),
    )
    walls = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Alicatado",
        quantity=Quantity.one(),
        unit_price=money("4000.00"),
        price_source=PriceSource.manual(),
    )
    advance = prior("3000.00", "630.00", 1, phase=PhaseType.ADVANCE)
    progress = prior("4000.00", "840.00", 2)
    plan = plan_final_phase(
        realized_lines=[floor.to_invoice_line()],
        prior_phases=[advance, progress],
        treatment=GENERAL,
        quote_lines=[floor, walls],
    )
    assert isinstance(plan, OverbillingPlan)
    assert plan.excess == money("1000.00")
    (proposal,) = plan.proposals
    assert proposal.base == money("-1000.00")
    assert proposal.breakdown.tax == money("-210.00")
    assert proposal.invoice_type is InvoiceType.R1
    assert proposal.correction_type is CorrectionType.DIFFERENCE
    # Rectifica la última fase emitida.
    assert [item.rectified for item in proposal.items] == [progress]
    # Y detalla lo que no se ha hecho.
    (removed,) = proposal.removed_works
    assert removed.description == "Alicatado"
    assert removed.removed_base == money("4000.00")


@pytest.mark.req("RN-F-12")
def test_si_la_ultima_fase_no_basta_se_rectifican_tambien_las_anteriores():
    advance = prior("3000.00", "630.00", 1, phase=PhaseType.ADVANCE)
    progress = prior("4000.00", "840.00", 2)
    plan = plan_final_phase(
        realized_lines=[realized("2000.00")],
        prior_phases=[advance, progress],
        treatment=GENERAL,
    )
    assert isinstance(plan, OverbillingPlan)
    (proposal,) = plan.proposals
    assert [(item.rectified, item.base) for item in proposal.items] == [
        (progress, money("-4000.00")),
        (advance, money("-1000.00")),
    ]
    assert proposal.removed_works == ()


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-F-13")
def test_una_rectificativa_por_tipo_si_las_fases_van_a_tipos_distintos():
    advance = prior("1000.00", "100.00", 1, treatment=REDUCED, phase=PhaseType.ADVANCE)
    progress = prior("1000.00", "210.00", 2)
    zero = prior("0.00", "0.00", 3)
    plan = plan_final_phase(
        realized_lines=[realized("500.00")],
        prior_phases=[advance, progress, zero],
        treatment=GENERAL,
    )
    assert isinstance(plan, OverbillingPlan)
    assert [(p.treatment, p.base) for p in plan.proposals] == [
        (GENERAL, money("-1000.00")),
        (REDUCED, money("-500.00")),
    ]
    # Tras rectificar, quedan 500 € del anticipo al 10 % con la obra al 21 %.
    (extra,) = plan.extra_vat
    assert extra.prior.base == money("500.00")
    assert extra.difference == money("55.00")


@pytest.mark.req("RN-F-13")
def test_material_supera_el_40_con_anticipo_ya_facturado_al_10():
    advance = prior("1000.00", "100.00", 1, treatment=REDUCED, phase=PhaseType.ADVANCE)
    plan = plan_final_phase(
        realized_lines=[realized("3000.00"), realized("2500.00", is_material=True)],
        prior_phases=[advance],
        treatment=GENERAL,
    )
    assert isinstance(plan, FinalPhasePlan)
    assert plan.treatment == GENERAL
    (extra,) = plan.extra_vat
    assert extra.prior == advance
    assert (extra.due_tax, extra.charged_tax) == (money("210.00"), money("100.00"))
    assert extra.difference == money("110.00")


@pytest.mark.req("RN-F-13")
def test_sin_iva_que_ingresar_si_el_tipo_no_sube():
    reduced = prior("1000.00", "100.00", 1, treatment=REDUCED)
    reverse = prior("1000.00", "0.00", 2, treatment=VatTreatment.reverse_charge())
    assert extra_vat_on_prior_phases([reduced], REDUCED) == ()
    assert extra_vat_on_prior_phases([reverse], GENERAL) == ()
    assert extra_vat_on_prior_phases([reduced], VatTreatment.reverse_charge()) == ()


@pytest.mark.req("RN-F-12")
def test_entradas_no_validas_de_la_final():
    progress = prior("100.00", "21.00", 1)
    with pytest.raises(InvalidPhaseError):
        plan_final_phase(realized_lines=[line("1.00")], prior_phases=[], treatment=GENERAL)
    with pytest.raises(InvalidPhaseError):
        plan_final_phase(
            realized_lines=[realized("1.00", outside_works=True)],
            prior_phases=[],
            treatment=GENERAL,
        )
    with pytest.raises(InvalidPhaseError):
        plan_final_phase(
            realized_lines=[realized("1.00")],
            prior_phases=[progress, progress],
            treatment=GENERAL,
        )
    with pytest.raises(InvalidPhaseError):
        plan_final_phase(realized_lines=[realized("-1.00")], prior_phases=[], treatment=GENERAL)
    with pytest.raises(InvalidPhaseError):
        prior("1.00", "0.21", 1, phase=PhaseType.FINAL)


@pytest.mark.req("RN-F-12")
def test_trabajos_quitados_en_parte():
    quoted = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Puntos de luz",
        quantity=Quantity.of(10),
        unit_price=money("45.00"),
        price_source=PriceSource.manual(),
    )
    unpriced = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Sin precio",
        quantity=Quantity.one(),
        unit_price=None,
        price_source=PriceSource.none(),
    )
    done = line("45.00", "6", origin=LineOrigin.QUOTE, quote_line_id=quoted.id)
    extra = realized("100.00", LineOrigin.ADDITIONAL)
    (removed,) = removed_works([quoted, unpriced], [done, extra])
    assert removed.quoted_base == money("450.00")
    assert removed.realized_base == money("270.00")
    assert removed.removed_base == money("180.00")
    assert (
        removed_works(
            [quoted], [line("45.00", "10", origin=LineOrigin.QUOTE, quote_line_id=quoted.id)]
        )
        == ()
    )


# ------------------------------------------------------------ lo pendiente


@pytest.mark.req("RN-F-11")
@pytest.mark.req("RF-FA-11")
def test_fase_superior_a_lo_pendiente():
    summary = billing_summary(money("10000.00"), [money("3000.00"), money("4000.00")])
    assert summary.pending == money("3000.00")
    warning = check_against_pending(summary, money("4000.00"))
    assert warning is not None
    assert (warning.pending, warning.excess) == (money("3000.00"), money("1000.00"))


@pytest.mark.req("RN-F-11")
@pytest.mark.req("RF-FA-12")
def test_trabajo_adicional_supera_lo_presupuestado():
    summary = billing_summary(money("6000.00"), [])
    warning = check_against_pending(summary, money("9000.00"))
    assert warning is not None
    assert warning.excess == money("3000.00")
    after = billing_summary(money("6000.00"), [money("9000.00")])
    assert after.difference == money("3000.00")
    assert after.pending == money("0.00")


@pytest.mark.req("RN-F-11")
def test_sin_aviso_si_no_supera_lo_pendiente():
    summary = billing_summary(money("10000.00"), [money("7000.00")])
    assert check_against_pending(summary, money("3000.00")) is None


@pytest.mark.req("RN-F-11")
def test_una_rectificativa_ajusta_lo_facturado():
    summary = billing_summary(money("10000.00"), [money("7000.00"), money("-1000.00")])
    assert summary.invoiced_base == money("6000.00")
    assert summary.pending == money("4000.00")


@pytest.mark.req("RN-F-13")
def test_el_iva_que_ingresar_no_se_corta_en_una_fase_que_no_lo_debe():
    reverse = prior("1000.00", "0.00", 1, treatment=VatTreatment.reverse_charge())
    general = prior("1000.00", "210.00", 2)
    reduced = prior("1000.00", "100.00", 3, treatment=REDUCED)
    extras = extra_vat_on_prior_phases([reverse, general, reduced], GENERAL)
    assert [extra.prior for extra in extras] == [reduced]


@pytest.mark.req("RN-F-12")
def test_trabajos_quitados_tras_una_linea_sin_precio():
    unpriced = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Pintura",
        quantity=Quantity.one(),
        unit_price=None,
        price_source=PriceSource.none(),
    )
    walls = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Alicatado",
        quantity=Quantity.one(),
        unit_price=money("4000.00"),
        price_source=PriceSource.manual(),
    )
    (removed,) = removed_works([unpriced, walls], [])
    assert removed.quote_line_id == walls.id
    assert removed.removed_base == money("4000.00")


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-F-13")
def test_el_iva_que_ingresar_tras_rectificar_cuenta_cada_fase_con_sus_datos():
    # La lista no va en orden: se rectifica la última emitida (la del día 2),
    # que aquí va en segundo lugar.
    earlier = prior("1000.00", "100.00", 1, treatment=REDUCED, phase=PhaseType.ADVANCE)
    later = prior("1000.00", "100.00", 2, treatment=REDUCED)
    plan = plan_final_phase(
        realized_lines=[realized("1500.00")],
        prior_phases=[earlier, later],
        treatment=GENERAL,
    )
    assert isinstance(plan, OverbillingPlan)
    assert [extra.prior for extra in plan.extra_vat] == [
        earlier,
        PriorPhase(
            invoice_id=later.invoice_id,
            number=later.number,
            issue_date=later.issue_date,
            phase_type=PhaseType.PROGRESS,
            base=money("500.00"),
            tax=money("50.00"),
            treatment=REDUCED,
        ),
    ]
