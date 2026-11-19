"""Pruebas de propiedades de la facturación por fases (RN-F-12, RN-F-13, ADR-033).

Sin trabajos adicionales ni cambios, la suma de las bases de las fases
(anticipo, certificaciones y final) es al céntimo la base del presupuesto,
sea cual sea el reparto. Si lo facturado supera el servicio, no hay final
negativa: sale una rectificativa por el exceso, y las fases más la
rectificativa vuelven a sumar el servicio prestado.

Las fases se construyen con las entidades del dominio (``Invoice.advance``,
borradores de certificación emitidos) y se pasan a ``plan_final_phase`` como
``PriorPhase``. Los repartos no dividen exacto a propósito: cantidades con
milésimas, descuentos y anticipos con IVA incluido.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from kapataz.domain.billing.codes import LineOrigin, PhaseType, RecipientType
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.numbering import Series
from kapataz.domain.billing.phases import (
    FinalPhasePlan,
    OverbillingPlan,
    PriorPhase,
    plan_final_phase,
)
from kapataz.domain.billing.quantity import MAX_QUANTITY, Percentage, Quantity
from kapataz.domain.billing.quote import PriceSource, QuoteLine, QuoteVersion
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.unit.domain.billing_factories import (
    CUSTOMER,
    GENERAL,
    NOW,
    REDUCED,
    TENANT,
    draft,
    issue,
)

SUPER_REDUCED = VatTreatment.taxed(TaxRate.super_reduced())
REVERSE = VatTreatment.reverse_charge()
TREATMENTS = (GENERAL, REDUCED, SUPER_REDUCED, REVERSE)
# Al emitir, el tipo se comprueba con el destinatario del presupuesto (RN-F-13):
# el 10 % solo con un particular, la inversión solo con un empresario.
PRIVATE_TREATMENTS = (GENERAL, REDUCED, SUPER_REDUCED)
BUSINESS_TREATMENTS = (GENERAL, SUPER_REDUCED, REVERSE)
RECIPIENTS_FOR = {
    treatment: tuple(
        recipient
        for recipient, allowed in (
            (RecipientType.PRIVATE, PRIVATE_TREATMENTS),
            (RecipientType.BUSINESS, BUSINESS_TREATMENTS),
        )
        if treatment in allowed
    )
    for treatment in TREATMENTS
}

MAX_QUANTITY_THOUSANDTHS = int(MAX_QUANTITY * 1000)
MAX_QUOTE_LINES = 8
MAX_PROGRESS_INVOICES = 5
MAX_PROGRESS_LINES = 3
# Tope de la base de cada línea del presupuesto (1.000.000,00 €). Con 8 líneas,
# cualquier reparto, el anticipo con IVA y el exceso caben en Money (ADR-009).
QUOTE_LINE_CAP_CENTS = 100_000_000
MAX_EXCESS_CENTS = 100_000_000
# Precio unitario máximo: el de Money (ADR-009).
MAX_PRICE_CENTS = 2_147_483_647
FIRST_ISSUE_DATE = date(2026, 1, 15)
HUNDREDTHS = 10_000


@dataclass(frozen=True, slots=True)
class Works:
    """Una obra presupuestada y sus fases ya emitidas, en el orden en que se emitieron."""

    treatment: VatTreatment
    quote_version: QuoteVersion
    advance_gross: Money | None
    phases: tuple[Invoice, ...]

    @property
    def prior_phases(self) -> tuple[PriorPhase, ...]:
        return tuple(_prior_phase(invoice) for invoice in self.phases)

    @property
    def prior_base(self) -> Money:
        return sum_money(invoice.totals.base for invoice in self.phases)


def _prior_phase(invoice: Invoice) -> PriorPhase:
    assert invoice.number is not None
    assert invoice.issue_date is not None
    assert invoice.phase_type is not None
    return PriorPhase(
        invoice_id=invoice.id,
        number=invoice.number,
        issue_date=invoice.issue_date,
        phase_type=invoice.phase_type,
        base=invoice.totals.base,
        tax=invoice.totals.tax,
        treatment=invoice.treatment,
    )


def _cents(amount: Money) -> int:
    return int(amount.amount * 100)


def _money(cents: int) -> Money:
    return Money(Decimal(cents).scaleb(-2))


def _quantity(thousandths: int) -> Quantity:
    return Quantity(Decimal(thousandths).scaleb(-3))


def _hundredths(percentage: Percentage | None) -> int:
    return 0 if percentage is None else int(percentage.value * 100)


# ------------------------------------------------------------ estrategias


@st.composite
def quote_lines(draw: st.DrawFn, index: int) -> QuoteLine:
    quantity_th = draw(
        st.one_of(
            st.integers(1, 999).map(lambda n: n * 1000),
            st.integers(1, MAX_QUANTITY_THOUSANDTHS),
        )
    )
    price_cap = max(1, min(QUOTE_LINE_CAP_CENTS * 1000 // quantity_th, MAX_PRICE_CENTS))
    discount = draw(st.none() | st.integers(0, HUNDREDTHS).map(lambda h: Percentage(_hd(h))))
    return QuoteLine(
        id=QuoteLineId(uuid4()),
        description=f"Partida {index + 1}",
        quantity=_quantity(quantity_th),
        unit_price=_money(draw(st.integers(1, price_cap))),
        price_source=PriceSource.manual(),
        discount=discount,
    )


def _hd(hundredths: int) -> Decimal:
    return Decimal(hundredths).scaleb(-2)


def _max_thousandths_within(remaining_cents: int, line: QuoteLine) -> int:
    """Mayor cantidad (en milésimas) de ``line`` cuyo importe exacto no pasa de lo que queda.

    Si cantidad × precio × (1 − descuento) ≤ lo que queda, la base redondeada
    tampoco lo pasa, porque lo que queda es un número exacto de céntimos.
    """
    assert line.unit_price is not None
    per_thousandth = _cents(line.unit_price) * (HUNDREDTHS - _hundredths(line.discount))
    if per_thousandth == 0:
        return MAX_QUANTITY_THOUSANDTHS
    return min(remaining_cents * 1000 * HUNDREDTHS // per_thousandth, MAX_QUANTITY_THOUSANDTHS)


def _progress_line(
    line: QuoteLine, quantity: Quantity, unit_price: Money | None = None
) -> LineItem:
    assert line.unit_price is not None
    return LineItem(
        description=line.description,
        quantity=quantity,
        unit_price=line.unit_price if unit_price is None else unit_price,
        discount=line.discount if unit_price is None else None,
        origin=LineOrigin.QUOTE,
        quote_line_id=line.id,
    )


@st.composite
def works(
    draw: st.DrawFn,
    *,
    budget: str = "quote",
    exceed: bool = False,
    mixed_treatments: bool = False,
) -> Works:
    """Obra con un reparto de fases cualquiera.

    - ``budget="quote"``: las fases no pasan de la base del presupuesto.
    - ``budget="free"``: el tope de lo facturado va de 0 al doble del presupuesto.
    - ``exceed``: una última certificación pasa lo que queda por facturar.
    - ``mixed_treatments``: cada fase con su propio tratamiento (la obra cambió
      de tipo), entre los que admite el destinatario del presupuesto.
    """
    treatment = draw(st.sampled_from(TREATMENTS))
    recipient_type = draw(st.sampled_from(RECIPIENTS_FOR[treatment]))
    private = recipient_type is RecipientType.PRIVATE
    count = draw(st.integers(1, MAX_QUOTE_LINES))
    lines = tuple(draw(quote_lines(index)) for index in range(count))
    version = QuoteVersion(
        id=QuoteVersionId(uuid4()),
        version=1,
        lines=lines,
        recipient_type=recipient_type,
        dwelling_over_two_years=True if private else None,
        valid_until=None,
        created_at=NOW,
    )
    allowed_treatments = PRIVATE_TREATMENTS if private else BUSINESS_TREATMENTS
    service_cents = _cents(version.base)
    if budget == "quote":
        remaining = service_cents
    else:
        remaining = draw(st.integers(0, 2 * service_cents + 10_000))

    def phase_treatment() -> VatTreatment:
        return draw(st.sampled_from(allowed_treatments)) if mixed_treatments else treatment

    drafts: list[Invoice] = []
    advance_gross: Money | None = None
    advance_treatment = phase_treatment()
    rate = 0 if advance_treatment.rate is None else int(advance_treatment.rate.percent)
    # Importe con IVA cuya base no pasa de lo que queda: importe ≤ queda × (1 + tipo).
    gross_cap = remaining * (100 + rate) // 100
    if gross_cap >= 1 and draw(st.booleans()):
        advance_gross = _money(draw(st.integers(1, gross_cap)))
        advance = Invoice.advance(
            id=InvoiceId(uuid4()),
            tenant_id=TENANT,
            customer_id=CUSTOMER,
            quote_version_id=version.id,
            series=Series.invoices(),
            treatment=advance_treatment,
            gross_amount=advance_gross,
            line_description="Anticipo a cuenta de la obra",
            created_at=NOW,
            description="Anticipo",
        )
        drafts.append(advance)
        remaining -= _cents(advance.totals.base)

    for _ in range(draw(st.integers(0, MAX_PROGRESS_INVOICES))):
        progress_lines: list[LineItem] = []
        for _ in range(draw(st.integers(1, MAX_PROGRESS_LINES))):
            line = draw(st.sampled_from(lines))
            max_th = _max_thousandths_within(remaining, line)
            if max_th < 1:
                continue
            item = _progress_line(line, _quantity(draw(st.integers(1, max_th))))
            progress_lines.append(item)
            remaining -= _cents(item.base)
        if progress_lines:
            drafts.append(_progress_draft(progress_lines, version.id, phase_treatment()))

    if exceed:
        over = remaining + draw(st.integers(1, MAX_EXCESS_CENTS))
        line = draw(st.sampled_from(lines))
        item = _progress_line(line, Quantity.one(), unit_price=_money(over))
        drafts.append(_progress_draft([item], version.id, phase_treatment()))

    issued = tuple(
        issue(
            invoice,
            sequence=index + 1,
            issue_date=FIRST_ISSUE_DATE + timedelta(days=index),
            version=version,
        )
        for index, invoice in enumerate(drafts)
    )
    return Works(
        treatment=treatment,
        quote_version=version,
        advance_gross=advance_gross,
        phases=issued,
    )


def _progress_draft(
    lines: list[LineItem], quote_version_id: QuoteVersionId, treatment: VatTreatment
) -> Invoice:
    return draft(
        *lines,
        treatment=treatment,
        description="Certificación de obra",
        phase_type=PhaseType.PROGRESS,
        quote_version_id=quote_version_id,
    )


@st.composite
def realized_lines(draw: st.DrawFn, version: QuoteVersion) -> list[LineItem]:
    """Trabajos realizados: cada partida entera, en menos cantidad o quitada. Sin adicionales."""
    realized: list[LineItem] = []
    for line in version.lines:
        match draw(st.sampled_from(("full", "less", "removed"))):
            case "full":
                realized.append(line.to_invoice_line())
            case "less":
                quantity_th = int(line.quantity.value * 1000)
                quantity = _quantity(draw(st.integers(1, quantity_th)))
                realized.append(_progress_line(line, quantity))
            case _:
                pass
    return realized


# ------------------------------------------------------------ comprobaciones


def _assert_advance_matches_gross(works_: Works) -> None:
    advances = [p for p in works_.phases if p.phase_type is PhaseType.ADVANCE]
    if works_.advance_gross is None:
        assert advances == []
        return
    (advance,) = advances
    assert advance.totals.base + advance.totals.tax == works_.advance_gross


def _assert_overbilling(plan: OverbillingPlan, prior_phases: tuple[PriorPhase, ...]) -> None:
    prior_base = sum_money(prior.base for prior in prior_phases)
    assert plan.prior_base == prior_base
    assert plan.excess == prior_base - plan.service_base
    assert plan.excess.is_positive()
    correction = sum_money(proposal.base for proposal in plan.proposals)
    assert correction == -plan.excess
    # Las fases más la rectificativa vuelven a sumar el servicio prestado.
    assert prior_base + correction == plan.service_base
    # Una rectificativa por tratamiento (RN-F-13), sin repetir ninguno.
    treatments = [proposal.treatment for proposal in plan.proposals]
    assert len(set(treatments)) == len(treatments)
    items = [item for proposal in plan.proposals for item in proposal.items]
    for proposal in plan.proposals:
        assert all(item.rectified.treatment == proposal.treatment for item in proposal.items)
    # Rectifica desde la última fase hacia atrás, y solo la última tocada en parte.
    latest_first = [
        prior
        for prior in sorted(prior_phases, key=lambda p: (p.issue_date, p.number), reverse=True)
        if prior.base.is_positive()
    ]
    rectified = sorted(items, key=lambda item: latest_first.index(item.rectified))
    assert [item.rectified for item in rectified] == latest_first[: len(rectified)]
    for item in rectified[:-1]:
        assert item.base == -item.rectified.base
    last = rectified[-1]
    assert last.base.is_negative()
    assert -last.base <= last.rectified.base


# ------------------------------------------------------------ propiedades


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-03")
@given(works_=works(budget="quote"), data=st.data())
def test_sin_cambios_la_suma_de_las_fases_cuadra_con_el_presupuesto(works_, data):
    version = works_.quote_version
    prior_phases = data.draw(st.permutations(works_.prior_phases))

    plan = plan_final_phase(
        realized_lines=[line.to_invoice_line() for line in version.lines],
        prior_phases=prior_phases,
        treatment=works_.treatment,
        quote_lines=version.lines,
    )

    assert isinstance(plan, FinalPhasePlan)
    assert plan.service_base == version.base
    assert plan.prior_base == works_.prior_base
    assert works_.prior_base + plan.base == version.base
    _assert_advance_matches_gross(works_)
    assert plan.extra_vat == ()
    # La final resta cada fase una vez, en orden cronológico y por su base.
    deductions = [line for line in plan.lines if line.origin is LineOrigin.PRIOR_INVOICE]
    assert [d.prior_invoice_id for d in deductions] == [p.id for p in works_.phases]
    assert [d.base for d in deductions] == [-p.totals.base for p in works_.phases]
    # De extremo a extremo: el borrador de la final da la misma base y cuota.
    final = draft(
        *plan.lines,
        treatment=plan.treatment,
        phase_type=PhaseType.FINAL,
        quote_version_id=version.id,
    )
    assert final.totals.base == plan.base
    assert final.totals.tax == plan.breakdown.tax
    event(f"fases anteriores: {len(works_.phases)}")


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-F-13")
@given(works_=works(budget="quote", exceed=True, mixed_treatments=True), data=st.data())
def test_si_lo_facturado_supera_el_presupuesto_se_rectifica_el_exceso(works_, data):
    version = works_.quote_version
    prior_phases = data.draw(st.permutations(works_.prior_phases))

    plan = plan_final_phase(
        realized_lines=[line.to_invoice_line() for line in version.lines],
        prior_phases=prior_phases,
        treatment=works_.treatment,
        quote_lines=version.lines,
    )

    assert isinstance(plan, OverbillingPlan)
    assert plan.service_base == version.base
    assert plan.excess == works_.prior_base - version.base
    _assert_overbilling(plan, works_.prior_phases)
    # Sin trabajos quitados, la rectificativa no detalla ninguno.
    assert all(proposal.removed_works == () for proposal in plan.proposals)
    _assert_advance_matches_gross(works_)


@pytest.mark.req("RN-F-12")
@given(works_=works(budget="free"), data=st.data())
def test_para_cualquier_reparto_las_fases_y_su_ajuste_suman_el_servicio_prestado(works_, data):
    version = works_.quote_version
    realized = data.draw(realized_lines(version))
    prior_phases = data.draw(st.permutations(works_.prior_phases))
    service_base = sum_money(line.base for line in realized)

    plan = plan_final_phase(
        realized_lines=realized,
        prior_phases=prior_phases,
        treatment=works_.treatment,
        quote_lines=version.lines,
    )

    assert plan.service_base == service_base
    assert plan.prior_base == works_.prior_base
    if works_.prior_base <= service_base:
        event("fase final")
        assert isinstance(plan, FinalPhasePlan)
        assert works_.prior_base + plan.base == service_base
        assert not plan.base.is_negative()
    else:
        event("rectificativa por el exceso")
        assert isinstance(plan, OverbillingPlan)
        _assert_overbilling(plan, works_.prior_phases)
        removed = {work.quote_line_id for work in plan.proposals[0].removed_works}
        realized_ids = {line.quote_line_id for line in realized}
        not_done = [
            line.id
            for line in version.lines
            if line.id not in realized_ids and line.priced_base is not None
            if line.priced_base.is_positive()
        ]
        assert all(line_id in removed for line_id in not_done)
