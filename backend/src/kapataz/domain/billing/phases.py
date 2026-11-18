"""Facturación por fases y control de lo facturado (RF-FA-10, RF-FA-11, RN-F-11 a RN-F-13, ADR-033).

Funciones puras sobre ``Money``. El anticipo se calcula con
``calculation.totals_from_gross`` (``Invoice.advance``); la certificación es una
factura normal con los trabajos realizados. Aquí está lo que mira varias
facturas a la vez:

- la fase final, que recoge todos los trabajos realizados y resta las bases de
  las fases anteriores citándolas;
- la rectificativa que se propone si lo facturado supera el servicio prestado;
- el IVA que el autónomo debe ingresar si la obra pasa del 10 % al 21 %;
- el resumen de lo facturado frente a lo presupuestado y el aviso al superar
  lo pendiente.

Sin trabajos adicionales ni cambios, la suma de las bases de las fases es
exactamente la base del presupuesto: la final es servicio − fases anteriores.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from kapataz.domain.billing.calculation import TaxBreakdown, tax_breakdown
from kapataz.domain.billing.codes import CorrectionType, InvoiceType, LineOrigin, PhaseType
from kapataz.domain.billing.errors import InvalidPhaseError
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.quote import QuoteLine
from kapataz.domain.billing.tax import VatTreatment

# Texto de la línea que resta una fase anterior en la factura final. Es
# contenido de la factura, no de la interfaz; si cambia, se cambia aquí.
PRIOR_INVOICE_LINE_TEMPLATE = "A deducir: factura {number} de {issue_date}"
# ADR-033, «Pendiente para cerrar», punto 3: clase provisional de la
# rectificativa que corrige fases facturadas de más (art. 80.Dos de la Ley
# del IVA), también cuando rectifica varias facturas.
OVERBILLING_INVOICE_TYPE = InvoiceType.R1
_PRIOR_PHASES = frozenset({PhaseType.ADVANCE, PhaseType.PROGRESS})
_REALIZED_ORIGINS = frozenset({LineOrigin.QUOTE, LineOrigin.ADDITIONAL})


@dataclass(frozen=True, slots=True, kw_only=True)
class PriorPhase:
    """Fase ya facturada (anticipo o certificación) de la misma obra.

    ``base`` y ``tax`` son netos: si una rectificativa ya la corrigió, van
    con la corrección aplicada (RN-F-11). ``treatment`` es el de esa factura.
    """

    invoice_id: InvoiceId
    number: DocumentNumber
    issue_date: date
    phase_type: PhaseType
    base: Money
    tax: Money
    treatment: VatTreatment

    def __post_init__(self) -> None:
        if self.phase_type not in _PRIOR_PHASES:
            raise InvalidPhaseError("Solo un anticipo o una certificación preceden a la final.")

    def deduction_line(self) -> LineItem:
        """Línea de la final que resta esta fase citándola (``origin`` = ``prior_invoice``)."""
        return LineItem(
            description=PRIOR_INVOICE_LINE_TEMPLATE.format(
                number=self.number,
                issue_date=self.issue_date.strftime("%d/%m/%Y"),
            ),
            quantity=Quantity.one(),
            unit_price=-self.base,
            origin=LineOrigin.PRIOR_INVOICE,
            prior_invoice_id=self.invoice_id,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtraVat:
    """IVA que el autónomo ingresa por una fase facturada a un tipo menor (RN-F-13).

    Lo ya facturado al 10 % a un particular no se rectifica al alza: el
    autónomo ingresa la diferencia (art. 89.Tres y Cinco de la Ley del IVA).
    """

    prior: PriorPhase
    due_tax: Money
    charged_tax: Money

    @property
    def difference(self) -> Money:
        return self.due_tax - self.charged_tax


def extra_vat_on_prior_phases(
    prior_phases: Iterable[PriorPhase], final: VatTreatment
) -> tuple[ExtraVat, ...]:
    """Diferencia de IVA de cada fase anterior facturada a un tipo menor que la final.

    Por fase: base × tipo de la final, redondeado, menos la cuota cobrada. Con
    un anticipo de 1.000 € al 10 % y la final al 21 %: 210 − 100 = 110 €.
    Solo cuenta si la final repercute IVA (S1): con inversión no hay cuota.
    """
    if final.is_reverse_charge:
        return ()
    extras: list[ExtraVat] = []
    for prior in prior_phases:
        if prior.treatment.is_reverse_charge or prior.treatment.effective_rate >= (
            final.effective_rate
        ):
            continue
        due = tax_breakdown(prior.base, final).tax
        extras.append(ExtraVat(prior=prior, due_tax=due, charged_tax=prior.tax))
    return tuple(extras)


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalPhasePlan:
    """Fase final (RN-F-12): servicio prestado menos las fases anteriores.

    ``lines`` son los trabajos realizados seguidos de una resta por cada fase
    anterior; con ellas se crea el borrador de la final. ``extra_vat`` es el
    IVA que hay que ingresar si la obra pasó a un tipo mayor.
    """

    treatment: VatTreatment
    lines: tuple[LineItem, ...]
    service_base: Money
    prior_base: Money
    extra_vat: tuple[ExtraVat, ...]

    @property
    def base(self) -> Money:
        return self.service_base - self.prior_base

    @property
    def breakdown(self) -> TaxBreakdown:
        return tax_breakdown(self.base, self.treatment)


@dataclass(frozen=True, slots=True, kw_only=True)
class RemovedWork:
    """Trabajo presupuestado que no se ha hecho, o se ha hecho en menos cantidad.

    La rectificativa lo detalla (RN-F-12). Es información, no una línea: la
    rectificativa corrige lo facturado de más, que puede ser menos que lo quitado.
    """

    quote_line_id: QuoteLineId
    description: str
    quoted_base: Money
    realized_base: Money

    @property
    def removed_base(self) -> Money:
        return self.quoted_base - self.realized_base


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectionItem:
    """Cuánto se rectifica de una fase: ``base`` es negativa."""

    rectified: PriorPhase
    base: Money


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectionProposal:
    """Rectificativa por diferencias que se propone, con un solo tratamiento de IVA.

    Rectifica la última fase emitida y, si su base no basta, también las
    anteriores (RN-F-12). Si esas fases van a tipos distintos, sale una
    propuesta por tipo, porque una factura lleva un solo tipo (RN-F-13).
    """

    treatment: VatTreatment
    items: tuple[CorrectionItem, ...]
    removed_works: tuple[RemovedWork, ...]
    invoice_type: InvoiceType = OVERBILLING_INVOICE_TYPE
    correction_type: CorrectionType = CorrectionType.DIFFERENCE

    @property
    def base(self) -> Money:
        return sum_money(item.base for item in self.items)

    @property
    def breakdown(self) -> TaxBreakdown:
        return tax_breakdown(self.base, self.treatment)


@dataclass(frozen=True, slots=True, kw_only=True)
class OverbillingPlan:
    """Lo facturado supera el servicio: no hay final negativa, hay rectificativa (RN-F-12)."""

    service_base: Money
    prior_base: Money
    proposals: tuple[CorrectionProposal, ...]
    extra_vat: tuple[ExtraVat, ...]

    @property
    def excess(self) -> Money:
        """Lo facturado de más, en positivo."""
        return self.prior_base - self.service_base


def plan_final_phase(
    *,
    realized_lines: Sequence[LineItem],
    prior_phases: Sequence[PriorPhase],
    treatment: VatTreatment,
    quote_lines: Sequence[QuoteLine] = (),
) -> FinalPhasePlan | OverbillingPlan:
    """Calcula la fase final o, si sale negativa, la rectificativa que la sustituye.

    - ``realized_lines``: todos los trabajos realizados, presupuestados o no
      (``origin`` ``quote`` o ``additional``), sin lo que va fuera de la obra.
    - ``prior_phases``: anticipos y certificaciones ya facturados, netos.
    - ``treatment``: el de la obra con los trabajos realizados (``works_vat``).
    - ``quote_lines``: las del presupuesto, para detallar lo que no se ha hecho.

    Con 10.000 € de servicio y 7.000 € facturados, la final tiene 3.000 € de
    base. Con 6.000 € de servicio, se propone rectificar -1.000 € de la última fase.
    """
    _check_final_inputs(realized_lines, prior_phases)
    service_base = sum_money(line.base for line in realized_lines)
    prior_base = sum_money(prior.base for prior in prior_phases)
    if service_base.is_negative():
        raise InvalidPhaseError("El servicio prestado no puede tener base negativa.")
    if service_base >= prior_base:
        deductions = tuple(prior.deduction_line() for prior in _chronological(prior_phases))
        return FinalPhasePlan(
            treatment=treatment,
            lines=(*realized_lines, *deductions),
            service_base=service_base,
            prior_base=prior_base,
            extra_vat=extra_vat_on_prior_phases(prior_phases, treatment),
        )
    items = _allocate_excess(prior_base - service_base, prior_phases)
    removed = removed_works(quote_lines, realized_lines)
    return OverbillingPlan(
        service_base=service_base,
        prior_base=prior_base,
        proposals=_group_by_treatment(items, removed),
        extra_vat=extra_vat_on_prior_phases(_after_corrections(prior_phases, items), treatment),
    )


def removed_works(
    quote_lines: Sequence[QuoteLine], realized_lines: Sequence[LineItem]
) -> tuple[RemovedWork, ...]:
    """Líneas del presupuesto con precio que no se han hecho, o solo en parte."""
    realized: dict[QuoteLineId, list[Money]] = {}
    for line in realized_lines:
        if line.quote_line_id is not None:
            realized.setdefault(line.quote_line_id, []).append(line.base)
    removed: list[RemovedWork] = []
    for quote_line in quote_lines:
        quoted = quote_line.priced_base
        if quoted is None:
            continue
        done = sum_money(realized.get(quote_line.id, ()))
        if done < quoted:
            removed.append(
                RemovedWork(
                    quote_line_id=quote_line.id,
                    description=quote_line.description,
                    quoted_base=quoted,
                    realized_base=done,
                )
            )
    return tuple(removed)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteBillingSummary:
    """Lo facturado frente a lo presupuestado (RF-FA-11, RN-F-11).

    ``invoiced_base`` incluye los borradores, que cuentan hasta que se
    eliminan, y las rectificativas, que ajustan lo facturado (RN-F-11).
    """

    quoted_base: Money
    invoiced_base: Money

    @property
    def pending(self) -> Money:
        """Lo que queda por facturar; nunca negativo."""
        remaining = self.quoted_base - self.invoiced_base
        return remaining if remaining.is_positive() else Money.zero()

    @property
    def difference(self) -> Money:
        """Facturado − presupuestado: positiva si se factura de más."""
        return self.invoiced_base - self.quoted_base


def billing_summary(quoted_base: Money, invoiced_bases: Iterable[Money]) -> QuoteBillingSummary:
    return QuoteBillingSummary(quoted_base=quoted_base, invoiced_base=sum_money(invoiced_bases))


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingExcess:
    """Aviso: la factura supera lo pendiente y hay que confirmarla (RN-F-11).

    «Quedan 3.000,00 € por facturar; esta fase lo supera en 1.000,00 €.» El
    texto lo pone la interfaz; aquí van las cifras.
    """

    pending: Money
    excess: Money


def check_against_pending(summary: QuoteBillingSummary, new_base: Money) -> PendingExcess | None:
    """Avisa si una factura nueva (o una fase) supera lo que queda por facturar.

    ``summary`` no incluye todavía la factura nueva.
    """
    excess = new_base - summary.pending
    if not excess.is_positive():
        return None
    return PendingExcess(pending=summary.pending, excess=excess)


def _check_final_inputs(
    realized_lines: Sequence[LineItem], prior_phases: Sequence[PriorPhase]
) -> None:
    if any(line.origin not in _REALIZED_ORIGINS for line in realized_lines):
        msg = "Los trabajos realizados son líneas del presupuesto o trabajo adicional."
        raise InvalidPhaseError(msg)
    if any(line.outside_works for line in realized_lines):
        raise InvalidPhaseError("Lo que no forma parte de la obra va en otra factura.")
    ids = [prior.invoice_id for prior in prior_phases]
    if len(set(ids)) != len(ids):
        raise InvalidPhaseError("Una fase anterior no se resta dos veces.")


def _chronological(prior_phases: Iterable[PriorPhase]) -> list[PriorPhase]:
    return sorted(prior_phases, key=lambda prior: (prior.issue_date, prior.number))


def _allocate_excess(excess: Money, prior_phases: Sequence[PriorPhase]) -> list[CorrectionItem]:
    """Reparte lo facturado de más desde la última fase hacia atrás."""
    items: list[CorrectionItem] = []
    remaining = excess
    for prior in reversed(_chronological(prior_phases)):
        if not remaining.is_positive():
            break
        if not prior.base.is_positive():
            continue
        amount = min(remaining, prior.base)
        items.append(CorrectionItem(rectified=prior, base=-amount))
        remaining -= amount
    return items


def _group_by_treatment(
    items: Sequence[CorrectionItem], removed: tuple[RemovedWork, ...]
) -> tuple[CorrectionProposal, ...]:
    groups: dict[VatTreatment, list[CorrectionItem]] = {}
    for item in items:
        groups.setdefault(item.rectified.treatment, []).append(item)
    return tuple(
        CorrectionProposal(treatment=treatment, items=tuple(group), removed_works=removed)
        for treatment, group in groups.items()
    )


def _after_corrections(
    prior_phases: Sequence[PriorPhase], items: Sequence[CorrectionItem]
) -> list[PriorPhase]:
    """Fases anteriores con la rectificación propuesta ya restada de su base y su cuota."""
    corrected = {item.rectified.invoice_id: item.base for item in items}
    adjusted: list[PriorPhase] = []
    for prior in prior_phases:
        delta = corrected.get(prior.invoice_id)
        if delta is None:
            adjusted.append(prior)
            continue
        base = prior.base + delta
        tax = prior.tax + tax_breakdown(delta, prior.treatment).tax
        adjusted.append(
            PriorPhase(
                invoice_id=prior.invoice_id,
                number=prior.number,
                issue_date=prior.issue_date,
                phase_type=prior.phase_type,
                base=base,
                tax=tax,
                treatment=prior.treatment,
            )
        )
    return adjusted
