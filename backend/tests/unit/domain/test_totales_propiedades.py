"""Pruebas de propiedades del cálculo de importes (RN-01, RN-03, RN-F-05, ADR-009).

Para cualquier combinación de líneas válida: la base de la factura es la suma
de las bases de línea, la cuota se redondea una vez sobre esa base y el total
es base + cuota, con la retención y la garantía redondeadas una vez cada una.
Si se parte de un importe con IVA incluido (el anticipo, RN-F-12), base +
cuota coincide al céntimo con ese importe.

Los resultados esperados no salen de las funciones del dominio: se calculan
aparte con ``Decimal`` y ``ROUND_HALF_UP`` (comprobando que el producto es
exacto) o con aritmética entera de céntimos.
"""

from decimal import ROUND_HALF_UP, Context, Decimal, Inexact, localcontext
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kapataz.domain.billing.calculation import (
    InvoiceTotals,
    line_base,
    tax_breakdown,
    tax_breakdown_from_gross,
    totals_from_gross,
    totals_from_lines,
)
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.ids import InvoiceId, QuoteVersionId
from kapataz.domain.billing.invoice import Guarantee, Invoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import Series
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.unit.domain.billing_factories import (
    CUSTOMER,
    GENERAL,
    NOW,
    REDUCED,
    TENANT,
    TODAY,
    draft,
)

SUPER_REDUCED = VatTreatment.taxed(TaxRate.super_reduced())
REVERSE = VatTreatment.reverse_charge()
TREATMENTS = (GENERAL, REDUCED, SUPER_REDUCED, REVERSE)
# Destinatario con el que cada tratamiento es válido en una factura sin presupuesto.
RECIPIENT_FOR = {
    GENERAL: (RecipientType.BUSINESS, None),
    REDUCED: (RecipientType.PRIVATE, True),
    SUPER_REDUCED: (RecipientType.BUSINESS, None),
    REVERSE: (RecipientType.BUSINESS, None),
}

CENT = Decimal("0.01")
# Máximo de Money en céntimos: el INTEGER de la base de datos (ADR-009, RN-01).
MAX_CENTS = 2_147_483_647
MAX_QUANTITY_THOUSANDTHS = 999_999_999
MAX_LINES = 20
# Tope de la base de cada línea (800.000,00 €): con 20 líneas y el 21 %, el
# total cabe en Money. Por encima, el dominio rechaza el importe por diseño.
LINE_CAP_CENTS = 80_000_000
# Precisión sobrada para que cantidad × precio × (1 − descuento) sea exacto.
ORACLE_PRECISION = 60


# ------------------------------------------------------------ estrategias


def _decimal(units: int, decimals: int) -> Decimal:
    return Decimal(units).scaleb(-decimals)


# Cantidad en milésimas: unidades enteras, cantidades pequeñas con decimales
# y el rango completo de Quantity.
thousandths = st.one_of(
    st.integers(1, 999).map(lambda n: n * 1000),
    st.integers(1, 10_000),
    st.integers(1, MAX_QUANTITY_THOUSANDTHS),
)
percentages = st.integers(0, 10_000).map(lambda c: Percentage(_decimal(c, 2)))
# Retención y garantía de una factura: mayores que 0 y menores que 100.
invoice_percentages = st.integers(1, 9_999).map(lambda c: Percentage(_decimal(c, 2)))
treatments = st.sampled_from(TREATMENTS)
gross_amounts = st.integers(1, MAX_CENTS).map(lambda c: Money(_decimal(c, 2)))


@st.composite
def lines(draw: st.DrawFn, *, allow_negative: bool = True) -> LineItem:
    """Línea válida cuya base no pasa de ``LINE_CAP_CENTS`` en valor absoluto.

    El precio se acota según la cantidad, así no hace falta descartar ejemplos.
    Un precio negativo es una línea que resta (``Quantity`` siempre es positiva).
    """
    quantity_th = draw(thousandths)
    price_cap = min(LINE_CAP_CENTS * 1000 // quantity_th, MAX_CENTS)
    price_cents = draw(st.integers(-price_cap if allow_negative else 0, price_cap))
    return LineItem(
        description="Trabajo",
        quantity=Quantity(_decimal(quantity_th, 3)),
        unit_price=Money(_decimal(price_cents, 2)),
        discount=draw(st.none() | percentages),
    )


line_lists = st.lists(lines(), max_size=MAX_LINES)


# ------------------------------------------------------------ oráculos


def _oracle_context() -> Context:
    """Contexto limpio: sin los indicadores que otra prueba del hilo haya dejado levantados.

    ``localcontext()`` sin argumento copia el contexto actual con sus indicadores; si
    una operación anterior del hilo levantó ``Inexact``, el oráculo fallaría sin motivo.
    """
    return Context(prec=ORACLE_PRECISION)


def _round(value: Decimal) -> Money:
    return Money(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _expected_line_base(line: LineItem) -> Money:
    with localcontext(_oracle_context()) as ctx:
        exact = line.quantity.value * line.unit_price.amount
        if line.discount is not None:
            exact = exact * (100 - line.discount.value) / 100
        assert not ctx.flags[Inexact]
        return _round(exact)


def _share(base: Money, percent: Decimal) -> Money:
    with localcontext(_oracle_context()) as ctx:
        exact = base.amount * percent / 100
        assert not ctx.flags[Inexact]
        return _round(exact)


def _rate_percent(treatment: VatTreatment) -> Decimal:
    return Decimal(0) if treatment.rate is None else treatment.rate.percent


def _expected_base_from_gross(gross: Money, treatment: VatTreatment) -> Money:
    """Base = importe / (1 + tipo), mitad hacia arriba, con enteros (importe > 0)."""
    numerator = int(gross.amount * 100) * 100
    denominator = 100 + int(_rate_percent(treatment))
    cents = (2 * numerator + denominator) // (2 * denominator)
    return Money(_decimal(cents, 2))


def _assert_valid_amount(amount: Money) -> None:
    # RN-01: Decimal con dos decimales exactos que cabe en céntimos INTEGER.
    assert type(amount.amount) is Decimal
    assert amount.amount.as_tuple().exponent == -2
    assert abs(int(amount.amount * 100)) <= MAX_CENTS


def _assert_totals(
    totals: InvoiceTotals,
    *,
    base: Money,
    treatment: VatTreatment,
    withholding_rate: Percentage | None,
    guarantee_rate: Percentage | None,
    expected_tax: Money | None = None,
) -> None:
    """Relaciones de RN-03 entre los importes; la cuota, por defecto, sobre la base."""
    if expected_tax is None:
        expected_tax = _share(base, _rate_percent(treatment))
    expected_withholding = (
        Money.zero() if withholding_rate is None else _share(base, withholding_rate.value)
    )
    expected_guarantee = (
        Money.zero() if guarantee_rate is None else _share(base, guarantee_rate.value)
    )
    assert totals.base == base
    assert totals.tax == expected_tax
    if treatment.is_reverse_charge:
        assert totals.tax.is_zero()
    assert totals.total_amount == totals.base + totals.tax
    assert totals.withholding == expected_withholding
    assert totals.guarantee == expected_guarantee
    assert totals.collectible == totals.total_amount - totals.withholding
    assert totals.amount_due == totals.collectible - totals.guarantee
    assert totals.amount_due + totals.guarantee + totals.withholding == totals.total_amount
    for amount in (
        totals.base,
        totals.tax,
        totals.total_amount,
        totals.withholding,
        totals.guarantee,
        totals.collectible,
        totals.amount_due,
    ):
        _assert_valid_amount(amount)


# ------------------------------------------------------------ desde las líneas


@pytest.mark.req("RN-03")
@pytest.mark.req("RN-01")
@pytest.mark.req("RN-F-05")
@given(
    items=line_lists,
    treatment=treatments,
    withholding_rate=st.none() | percentages,
    guarantee_rate=st.none() | percentages,
)
def test_bases_y_cuotas_cuadran_con_el_total_para_cualquier_combinacion_de_lineas(
    items, treatment, withholding_rate, guarantee_rate
):
    bases = [line_base(item.quantity, item.unit_price, item.discount) for item in items]
    for item, base in zip(items, bases, strict=True):
        assert base == _expected_line_base(item)
        _assert_valid_amount(base)
    expected_base = Money(sum((base.amount for base in bases), Decimal("0.00")))

    totals = totals_from_lines(bases, treatment, withholding_rate, guarantee_rate)

    _assert_totals(
        totals,
        base=expected_base,
        treatment=treatment,
        withholding_rate=withholding_rate,
        guarantee_rate=guarantee_rate,
    )


@pytest.mark.req("RN-03")
@given(items=st.lists(lines(), min_size=1, max_size=MAX_LINES), treatment=treatments)
def test_el_orden_de_las_lineas_no_cambia_los_totales(items, treatment):
    forward = totals_from_lines((item.base for item in items), treatment)
    backward = totals_from_lines((item.base for item in reversed(items)), treatment)
    assert forward == backward


@pytest.mark.req("RN-03")
@pytest.mark.req("RN-F-05")
@given(
    items=line_lists,
    treatment=treatments,
    withholding_rate=st.none() | invoice_percentages,
    guarantee_rate=st.none() | invoice_percentages,
)
def test_los_totales_de_la_factura_cuadran_de_extremo_a_extremo(
    items, treatment, withholding_rate, guarantee_rate
):
    recipient_type, dwelling = RECIPIENT_FOR[treatment]
    invoice = draft(
        *items,
        treatment=treatment,
        recipient_type=recipient_type,
        dwelling_over_two_years=dwelling,
    ).with_withholding(withholding_rate)
    if guarantee_rate is not None:
        invoice = invoice.with_guarantee(Guarantee(rate=guarantee_rate, due_date=TODAY))

    totals = invoice.totals

    expected_base = Money(
        sum((_expected_line_base(item).amount for item in items), Decimal("0.00"))
    )
    _assert_totals(
        totals,
        base=expected_base,
        treatment=treatment,
        withholding_rate=withholding_rate,
        guarantee_rate=guarantee_rate,
    )


# ------------------------------------------------------------ desde un importe con IVA


@pytest.mark.req("RN-03")
@pytest.mark.req("RN-F-05")
@pytest.mark.req("RN-F-12")
@given(gross=gross_amounts, treatment=treatments, withholding_rate=st.none() | percentages)
def test_desde_un_importe_con_iva_base_mas_cuota_es_el_importe(gross, treatment, withholding_rate):
    breakdown = tax_breakdown_from_gross(gross, treatment)

    assert breakdown.base == _expected_base_from_gross(gross, treatment)
    assert breakdown.base + breakdown.tax == gross
    assert breakdown.total == gross
    if treatment.is_reverse_charge:
        assert (breakdown.base, breakdown.tax) == (gross, Money.zero())
    # La cuota es la diferencia; aun así, no se aleja más de un céntimo de la
    # que daría la regla general sobre la misma base.
    general_rule_tax = tax_breakdown(breakdown.base, treatment).tax
    assert abs(breakdown.tax - general_rule_tax) <= Money(CENT)

    totals = totals_from_gross(gross, treatment, withholding_rate)

    assert totals.breakdown == breakdown
    assert totals.total_amount == gross
    assert totals.guarantee == Money.zero()
    expected_withholding = (
        Money.zero() if withholding_rate is None else _share(breakdown.base, withholding_rate.value)
    )
    assert totals.withholding == expected_withholding
    assert totals.collectible == gross - expected_withholding
    assert totals.amount_due == totals.collectible
    for amount in (totals.base, totals.tax, totals.withholding, totals.amount_due):
        _assert_valid_amount(amount)


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RN-03")
@given(
    gross=gross_amounts,
    treatment=treatments,
    withholding_rate=st.none() | invoice_percentages,
)
def test_el_anticipo_cuadra_al_centimo_con_lo_cobrado(gross, treatment, withholding_rate):
    invoice = Invoice.advance(
        id=InvoiceId(uuid4()),
        tenant_id=TENANT,
        customer_id=CUSTOMER,
        quote_version_id=QuoteVersionId(uuid4()),
        series=Series.invoices(),
        treatment=treatment,
        gross_amount=gross,
        line_description="Anticipo",
        created_at=NOW,
        description="Anticipo de la obra",
        withholding_rate=withholding_rate,
    )

    totals = invoice.totals

    assert totals.base + totals.tax == gross
    assert totals.base == _expected_base_from_gross(gross, treatment)
    (line,) = invoice.lines
    assert line.base == totals.base
    # Excepción de RN-03: la cuota es la diferencia entre lo cobrado y la base.
    _assert_totals(
        totals,
        base=totals.base,
        treatment=treatment,
        withholding_rate=withholding_rate,
        guarantee_rate=None,
        expected_tax=gross - totals.base,
    )
