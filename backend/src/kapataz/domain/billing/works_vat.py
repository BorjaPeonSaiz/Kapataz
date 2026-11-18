"""Tipo de IVA de la obra y separación por tipos (RN-F-13, ADR-033).

El tipo se decide para la obra entera, no por línea: material, mano de obra y
anticipos llevan el mismo. Va al 10 % si el destinatario es una persona física
que usa la vivienda para fines particulares o una comunidad de propietarios,
la vivienda se terminó al menos dos años antes y el material que aporta el
autónomo no supera el 40 % de la base. Si no, al 21 %.

Decisión provisional (ADR-033, «Pendiente para cerrar»): el 40 % se calcula
sobre la base de las líneas de la obra, sin las que van fuera de ella
(``outside_works``) ni las que restan facturas anteriores. Si el asesor fiscal
indica otra base, se cambia ``material_share`` y nada más.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Protocol

from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.errors import InvalidTaxRateError
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.tax import TaxRate, VatTreatment

# Art. 91.Uno.2.10º de la Ley del IVA: el material no puede exceder el 40 %.
MATERIAL_LIMIT = Fraction(40, 100)
# Desde aquí se avisa antes de facturar al 10 % (RN-F-13).
MATERIAL_WARNING_THRESHOLD = Fraction(35, 100)
_ELIGIBLE_RECIPIENTS = frozenset({RecipientType.PRIVATE, RecipientType.COMMUNITY})


class WorksLine(Protocol):
    """Lo que hace falta de una línea, de presupuesto o de factura, para el 40 %."""

    @property
    def is_material(self) -> bool: ...

    @property
    def counts_for_works(self) -> bool: ...

    @property
    def priced_base(self) -> Money | None: ...


@dataclass(frozen=True, slots=True)
class MaterialShare:
    """Peso del material en la base de la obra.

    Las comparaciones con el 35 % y el 40 % se hacen con la fracción exacta;
    ``percent`` solo es para mostrarlo (redondeado a dos decimales).
    """

    works_base: Money
    material_base: Money

    @property
    def ratio(self) -> Fraction | None:
        """None si la obra no tiene base positiva: no hay peso que calcular."""
        if not self.works_base.is_positive():
            return None
        return self.material_base.as_fraction() / self.works_base.as_fraction()

    @property
    def percent(self) -> Decimal | None:
        ratio = self.ratio
        if ratio is None:
            return None
        # Mismo criterio que los importes (mitad hacia arriba), pero no es un
        # importe: no pasa por Money.
        hundredths = int(abs(ratio) * 10_000 + Fraction(1, 2))
        return Decimal(-hundredths if ratio < 0 else hundredths).scaleb(-2)

    @property
    def exceeds_limit(self) -> bool:
        """«No supera el 40 %»: el 40 % justo todavía admite el 10 %."""
        ratio = self.ratio
        return ratio is not None and ratio > MATERIAL_LIMIT

    @property
    def near_limit(self) -> bool:
        """Del 35 % («llega al 35 %», incluido) al 40 %, también incluido."""
        ratio = self.ratio
        return ratio is not None and MATERIAL_WARNING_THRESHOLD <= ratio <= MATERIAL_LIMIT


def material_share(lines: Iterable[WorksLine]) -> MaterialShare:
    """Base de la obra y del material, con las líneas que tienen precio.

    Una línea de presupuesto sin precio (RN-06) no cuenta: el aviso se
    recalcula cuando se le pone precio.
    """
    works: list[Money] = []
    material: list[Money] = []
    for line in lines:
        base = line.priced_base
        if base is None or not line.counts_for_works:
            continue
        works.append(base)
        if line.is_material:
            material.append(base)
    return MaterialShare(sum_money(works), sum_money(material))


class VatRateReason(StrEnum):
    """Por qué la obra no va al 10 %. La pantalla lo explica con su texto (i18n)."""

    RECIPIENT_NOT_ELIGIBLE = "recipient_not_eligible"
    DWELLING_TOO_RECENT = "dwelling_too_recent"
    MATERIAL_OVER_LIMIT = "material_over_limit"


@dataclass(frozen=True, slots=True)
class WorksVatDecision:
    """Tipo de la obra, motivos si no es el reducido y peso del material.

    ``warn_material_near_limit``: avisar antes de facturar al 10 % porque el
    material ya llega al 35 % de la base (RN-F-13).
    """

    rate: TaxRate
    reasons: tuple[VatRateReason, ...]
    material: MaterialShare

    @property
    def is_reduced(self) -> bool:
        return self.rate == TaxRate.reduced()

    @property
    def warn_material_near_limit(self) -> bool:
        return self.is_reduced and self.material.near_limit


def decide_works_vat(
    recipient_type: RecipientType,
    dwelling_over_two_years: bool,  # noqa: FBT001
    material: MaterialShare,
) -> WorksVatDecision:
    """Decide el tipo de IVA de la obra entera (RN-F-13).

    Se llama con las líneas del presupuesto para el anticipo y la
    certificación, y con los trabajos realizados para la fase final o la
    factura completa. Si el material supera el 40 % al final, toda la obra
    pasa al 21 % (ver ``phases.extra_vat_on_prior_phases``).
    """
    reasons: list[VatRateReason] = []
    if recipient_type not in _ELIGIBLE_RECIPIENTS:
        reasons.append(VatRateReason.RECIPIENT_NOT_ELIGIBLE)
    if not dwelling_over_two_years:
        reasons.append(VatRateReason.DWELLING_TOO_RECENT)
    if material.exceeds_limit:
        reasons.append(VatRateReason.MATERIAL_OVER_LIMIT)
    rate = TaxRate.general() if reasons else TaxRate.reduced()
    return WorksVatDecision(rate, tuple(reasons), material)


def works_treatment(
    decision: WorksVatDecision,
    recipient_type: RecipientType,
    *,
    reverse_charge: bool,
) -> VatTreatment:
    """Tratamiento de la factura de la obra.

    La inversión del sujeto pasivo la elige el profesional (obra entre
    empresas, RF-FA-05), y solo cabe si el destinatario es un empresario: a un
    particular o a una comunidad nunca se le invierte el sujeto pasivo.
    """
    if not reverse_charge:
        return VatTreatment.taxed(decision.rate)
    if recipient_type is not RecipientType.BUSINESS:
        msg = "La inversión del sujeto pasivo solo cabe con un empresario como destinatario."
        raise InvalidTaxRateError(msg)
    return VatTreatment.reverse_charge()


@dataclass(frozen=True, slots=True)
class VatGroup:
    """Líneas que irán en una misma factura, con su tratamiento."""

    treatment: VatTreatment
    lines: tuple[LineItem, ...]


def split_by_vat(lines: Sequence[LineItem], works: VatTreatment) -> tuple[VatGroup, ...]:
    """Reparte las líneas en una factura por tratamiento de IVA (RN-F-13).

    La obra va con su tratamiento; lo que no forma parte de ella, al 21 % sin
    inversión. Si los dos coinciden, sale una sola factura. Primero la obra.
    """
    outside = VatTreatment.taxed(TaxRate.general())
    works_lines = tuple(line for line in lines if not line.outside_works)
    outside_lines = tuple(line for line in lines if line.outside_works)
    if works == outside:
        groups = [VatGroup(works, works_lines + outside_lines)]
    else:
        groups = [VatGroup(works, works_lines), VatGroup(outside, outside_lines)]
    return tuple(group for group in groups if group.lines)
