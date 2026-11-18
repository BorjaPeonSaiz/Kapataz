"""Cobros: estado de cobro, tope de lo pendiente y aviso del efectivo (RN-F-10, RN-F-13)."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.errors import InvalidPaymentError, PaymentExceedsPendingError
from kapataz.domain.billing.ids import InvoiceId, PaymentId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.payment import (
    Payment,
    PaymentMethod,
    PaymentStatus,
    check_payment,
    payment_status,
    pending_amount,
    warns_cash_on_reduced_works,
)
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.unit.domain.billing_factories import GENERAL, REDUCED, money

NOW = datetime(2026, 11, 18, tzinfo=UTC)


def payment(amount: str, method: PaymentMethod = PaymentMethod.TRANSFER) -> Payment:
    return Payment(
        id=PaymentId(uuid4()),
        tenant_id=TenantId(uuid4()),
        invoice_id=InvoiceId(uuid4()),
        amount=money(amount),
        paid_at=date(2026, 11, 18),
        method=method,
        created_at=NOW,
    )


@pytest.mark.req("RN-F-10")
def test_cobro_superior_al_pendiente():
    with pytest.raises(PaymentExceedsPendingError) as error:
        check_payment(money("500.00"), [payment("380.00")], money("200.00"))
    assert error.value.pending == money("120.00")
    assert "Quedan 120.00 € por cobrar" in str(error.value)


@pytest.mark.req("RN-F-10")
def test_cobro_igual_al_pendiente():
    check_payment(money("500.00"), [payment("380.00")], money("120.00"))
    assert pending_amount(money("500.00"), [payment("380.00"), payment("120.00")]).is_zero()


@pytest.mark.req("RF-FA-06")
def test_estado_de_cobro():
    total = money("500.00")
    assert payment_status(total, []) is PaymentStatus.PENDING
    assert payment_status(total, [payment("100.00")]) is PaymentStatus.PARTIALLY_PAID
    assert payment_status(total, [payment("400.00"), payment("100.00")]) is PaymentStatus.PAID


@pytest.mark.req("RF-FA-06")
def test_cobros_no_validos():
    with pytest.raises(InvalidPaymentError):
        payment("0.00")
    with pytest.raises(InvalidPaymentError):
        payment("-1.00")
    with pytest.raises(InvalidPaymentError):
        Payment(
            id=PaymentId(uuid4()),
            tenant_id=TenantId(uuid4()),
            invoice_id=InvoiceId(uuid4()),
            amount=Money.of("1.00"),
            paid_at=date(2026, 1, 1),
            method=PaymentMethod.CARD,
            created_at=datetime(2026, 1, 1),  # noqa: DTZ001
        )


@pytest.mark.req("RN-F-13")
def test_cobro_en_efectivo_de_una_obra_al_10():
    assert warns_cash_on_reduced_works(REDUCED, PaymentMethod.CASH)


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    ("treatment", "method"),
    [
        (REDUCED, PaymentMethod.CARD),
        (REDUCED, PaymentMethod.TRANSFER),
        (REDUCED, PaymentMethod.CHEQUE),
        (REDUCED, PaymentMethod.DEPOSIT),
        (GENERAL, PaymentMethod.CASH),
        (VatTreatment.taxed(TaxRate.super_reduced()), PaymentMethod.CASH),
        (VatTreatment.reverse_charge(), PaymentMethod.CASH),
    ],
)
def test_sin_aviso_fuera_del_efectivo_al_10(treatment, method):
    assert not warns_cash_on_reduced_works(treatment, method)
