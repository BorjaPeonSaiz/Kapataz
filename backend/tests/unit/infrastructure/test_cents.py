"""Conversor único entre Money y céntimos (ADR-009) y adaptador nulo de envío (ADR-012)."""

import asyncio
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.dialects import postgresql

from kapataz.domain.billing.money import MAX_ABS_AMOUNT, Money
from kapataz.infrastructure.fiscal.null_submission import NullBillingRecordSubmission
from kapataz.infrastructure.persistence.money import Cents, cents_to_money, money_to_cents

_MAX_CENTS = int(MAX_ABS_AMOUNT * 100)
_DIALECT = postgresql.dialect()


@pytest.mark.req("RN-01")
@pytest.mark.parametrize(
    ("amount", "cents"),
    [
        ("0.00", 0),
        ("0.01", 1),
        ("-0.01", -1),
        ("1512.50", 151250),
        ("21474836.47", 2_147_483_647),
        ("-21474836.47", -2_147_483_647),
    ],
)
def test_money_y_centimos_ida_y_vuelta(amount, cents):
    money = Money.of(amount)
    assert money_to_cents(money) == cents
    assert cents_to_money(cents) == money
    assert str(cents_to_money(cents)) == f"{Decimal(amount):.2f}"


@pytest.mark.req("RN-01")
@given(st.integers(min_value=-_MAX_CENTS, max_value=_MAX_CENTS))
def test_cualquier_importe_admitido_vuelve_sin_perdida(cents):
    assert money_to_cents(cents_to_money(cents)) == cents


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", [1.5, Decimal(1), "100", True])
def test_los_centimos_solo_son_enteros(value):
    with pytest.raises(TypeError):
        cents_to_money(value)


@pytest.mark.req("RN-01")
def test_la_columna_cents_convierte_en_los_dos_sentidos():
    column = Cents()
    assert column.process_bind_param(Money.of("45.90"), _DIALECT) == 4590
    assert column.process_bind_param(None, _DIALECT) is None
    assert column.process_result_value(4590, _DIALECT) == Money.of("45.90")
    assert column.process_result_value(None, _DIALECT) is None


@pytest.mark.req("RN-01")
@pytest.mark.parametrize("value", [45.9, 4590, Decimal("45.90")])
def test_la_columna_cents_solo_admite_money(value):
    with pytest.raises(TypeError):
        Cents().process_bind_param(value, _DIALECT)


# Sin req: el adaptador nulo no tiene comportamiento que trazar; la llamada desde la
# emisión la cubre test_issue_invoice.py (RF-VF-01).
def test_el_adaptador_nulo_no_hace_nada():
    assert asyncio.run(NullBillingRecordSubmission().submit(object())) is None  # type: ignore[arg-type]
