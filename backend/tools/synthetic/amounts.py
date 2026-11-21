"""Importes de un documento y su versión impresa con el error sembrado (ADR-020).

Los importes correctos salen de las funciones del dominio (``Money.round``, un
solo redondeo por línea y por cuota, RN-03). Los impresos son los correctos
salvo en los documentos con error sembrado, donde se comete el error de forma
determinista según ``error_variant``.

«Total» es el total de la factura tal como se imprime en España: base + cuota −
retención de IRPF. La retención de garantía no lo cambia: solo aplaza el cobro,
y se imprime aparte junto al líquido a percibir (``amount_due``).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction

from kapataz.domain.billing.money import Money
from synthetic.model import LineData, SeededErrorKind

_HUNDRED = Fraction(100)
# Diferencia que se suma al total cuando trasponer cifras no cambia nada (1.111,00).
_TOTAL_SLIP = Decimal("10.00")


@dataclass(frozen=True, slots=True, kw_only=True)
class VatBucket:
    """Una fila del desglose de IVA: tipo (None con inversión), base y cuota."""

    rate: Decimal | None
    base: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Totals:
    """Importes de un documento. ``lines`` son los importes de cada línea, en orden."""

    lines: tuple[Decimal, ...]
    buckets: tuple[VatBucket, ...]
    base: Decimal
    vat_amount: Decimal
    reverse_charge: bool
    withholding_rate: Decimal | None
    withholding: Decimal | None
    guarantee_rate: Decimal | None
    guarantee: Decimal | None
    total: Decimal
    amount_due: Decimal

    @property
    def single_rate(self) -> Decimal | None:
        """El tipo si hay uno solo; None con inversión o con varios tipos."""
        rates = {bucket.rate for bucket in self.buckets}
        if len(rates) != 1:
            return None
        return next(iter(rates))


def percent_of(base: Decimal, rate: Decimal) -> Decimal:
    """Porcentaje de un importe con un solo redondeo, como el dominio (RN-03)."""
    return Money.round(Fraction(base) * Fraction(rate) / _HUNDRED).amount


def compute_totals(
    lines: Sequence[LineData],
    *,
    reverse_charge: bool,
    withholding_rate: Decimal | None,
    guarantee_rate: Decimal | None,
) -> Totals:
    """Importes correctos: base por tipo, cuota por tipo, retenciones y total."""
    amounts = tuple(line.amount for line in lines)
    rates: list[Decimal | None] = []
    for line in lines:
        if line.vat_rate not in rates:
            rates.append(line.vat_rate)
    buckets: list[VatBucket] = []
    for rate in rates:
        base = sum(
            (amount for line, amount in zip(lines, amounts, strict=True) if line.vat_rate == rate),
            Decimal("0.00"),
        )
        tax = Decimal("0.00") if rate is None else percent_of(base, rate)
        buckets.append(VatBucket(rate=rate, base=base, amount=tax))
    base = sum(amounts, Decimal("0.00"))
    return _with_derived(
        lines=amounts,
        buckets=tuple(buckets),
        base=base,
        reverse_charge=reverse_charge,
        withholding_rate=withholding_rate,
        guarantee_rate=guarantee_rate,
    )


def _with_derived(
    *,
    lines: tuple[Decimal, ...],
    buckets: tuple[VatBucket, ...],
    base: Decimal,
    reverse_charge: bool,
    withholding_rate: Decimal | None,
    guarantee_rate: Decimal | None,
) -> Totals:
    vat_amount = sum((bucket.amount for bucket in buckets), Decimal("0.00"))
    withholding = None if withholding_rate is None else percent_of(base, withholding_rate)
    guarantee = None if guarantee_rate is None else percent_of(base, guarantee_rate)
    total = base + vat_amount - (withholding or Decimal(0))
    return Totals(
        lines=lines,
        buckets=buckets,
        base=base,
        vat_amount=vat_amount,
        reverse_charge=reverse_charge,
        withholding_rate=withholding_rate,
        withholding=withholding,
        guarantee_rate=guarantee_rate,
        guarantee=guarantee,
        total=total,
        amount_due=total - (guarantee or Decimal(0)),
    )


def printed_totals(totals: Totals, error: SeededErrorKind | None, variant: int) -> Totals:
    """Lo que imprime el documento: los importes correctos o con el error sembrado.

    - ``total_no_cuadra``: el total lleva dos cifras traspuestas (variante par)
      o se olvida de restar la retención o suma diez euros de más (impar).
    - ``base_no_cuadra``: la base se olvida de la última línea; la cuota y el
      total se calculan bien sobre esa base equivocada.
    - ``cuota_iva_no_cuadra``: la cuota se calcula con el otro tipo (par) o se
      trunca en vez de redondear (impar, si eso cambia el céntimo); el total
      suma la cuota impresa.
    """
    match error:
        case SeededErrorKind.TOTAL_MISMATCH:
            total = _wrong_total(totals, variant)
            return replace(totals, total=total, amount_due=total - (totals.guarantee or Decimal(0)))
        case SeededErrorKind.BASE_MISMATCH:
            return _wrong_base(totals)
        case SeededErrorKind.VAT_MISMATCH:
            return _wrong_vat(totals, variant)
        case _:
            return totals


def _wrong_total(totals: Totals, variant: int) -> Decimal:
    if variant % 2 == 1:
        if totals.withholding is not None:
            return totals.total + totals.withholding
        return totals.total + _TOTAL_SLIP
    swapped = _swap_digits(totals.total)
    return swapped if swapped != totals.total else totals.total + _TOTAL_SLIP


def _swap_digits(value: Decimal) -> Decimal:
    """Traspone las dos últimas cifras distintas de la parte entera (1.243 → 1.234)."""
    text = f"{value:.2f}"
    integer, cents = text.split(".")
    digits = list(integer)
    for index in range(len(digits) - 1, 0, -1):
        if digits[index] != digits[index - 1]:
            digits[index], digits[index - 1] = digits[index - 1], digits[index]
            break
    if digits[0] == "0" and len(digits) > 1:
        return value
    return Decimal(f"{''.join(digits)}.{cents}")


def _wrong_base(totals: Totals) -> Totals:
    if len(totals.buckets) != 1 or len(totals.lines) < 2:  # noqa: PLR2004
        raise ValueError("La base errónea se siembra en documentos de un tipo y varias líneas.")
    bucket = totals.buckets[0]
    base = totals.base - totals.lines[-1]
    tax = Decimal("0.00") if bucket.rate is None else percent_of(base, bucket.rate)
    return _with_derived(
        lines=totals.lines,
        buckets=(VatBucket(rate=bucket.rate, base=base, amount=tax),),
        base=base,
        reverse_charge=totals.reverse_charge,
        withholding_rate=totals.withholding_rate,
        guarantee_rate=totals.guarantee_rate,
    )


def _wrong_vat(totals: Totals, variant: int) -> Totals:
    bucket = totals.buckets[0]
    rate = bucket.rate
    if len(totals.buckets) != 1 or rate is None:
        raise ValueError("La cuota errónea se siembra en documentos de un solo tipo de IVA.")
    wrong = _truncated(bucket.base, rate)
    if variant % 2 == 0 or wrong == bucket.amount:
        other = Decimal(21) if rate != Decimal(21) else Decimal(10)
        wrong = percent_of(bucket.base, other)
    return _with_derived(
        lines=totals.lines,
        buckets=(VatBucket(rate=bucket.rate, base=bucket.base, amount=wrong),),
        base=totals.base,
        reverse_charge=totals.reverse_charge,
        withholding_rate=totals.withholding_rate,
        guarantee_rate=totals.guarantee_rate,
    )


def _truncated(base: Decimal, rate: Decimal) -> Decimal:
    exact = Fraction(base) * Fraction(rate) / _HUNDRED
    cents = int(exact * 100)
    return Decimal(cents).scaleb(-2)
