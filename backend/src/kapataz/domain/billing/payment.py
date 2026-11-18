"""Cobros de facturas (``Payment``, RF-FA-06, RN-F-10, RN-F-13).

El estado de cobro es independiente del fiscal: sale de los cobros
registrados, no de la factura, que una vez emitida no cambia (RN-F-02).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.errors import InvalidPaymentError, PaymentExceedsPendingError
from kapataz.domain.billing.ids import InvoiceId, PaymentId
from kapataz.domain.billing.money import Money, sum_money
from kapataz.domain.billing.tax import TaxRate, VatTreatment


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    BIZUM = "bizum"
    CHEQUE = "cheque"
    DEPOSIT = "deposit"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"


@dataclass(frozen=True, slots=True, kw_only=True)
class Payment:
    """Cobro recibido de una factura, con fecha y forma de pago."""

    id: PaymentId
    tenant_id: TenantId
    invoice_id: InvoiceId
    amount: Money
    paid_at: date
    method: PaymentMethod
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.amount.is_positive():
            raise InvalidPaymentError("Un cobro es un importe mayor que cero.")
        if self.created_at.tzinfo is None:
            raise InvalidPaymentError("La fecha de registro debe llevar zona horaria.")


def pending_amount(collectible: Money, payments: Iterable[Payment]) -> Money:
    """Lo que queda por cobrar: total menos retención, menos lo ya cobrado.

    ``collectible`` es ``InvoiceTotals.collectible``: incluye la garantía,
    que se cobra al vencer (RF-FA-15), pero no la retención de IRPF, que el
    cliente ingresa en Hacienda.
    """
    return collectible - sum_money(payment.amount for payment in payments)


def check_payment(collectible: Money, payments: Iterable[Payment], amount: Money) -> None:
    """RN-F-10: rechaza un cobro mayor que lo pendiente, diciendo cuánto queda."""
    pending = pending_amount(collectible, payments)
    if amount > pending:
        raise PaymentExceedsPendingError(pending)


def payment_status(collectible: Money, payments: Iterable[Payment]) -> PaymentStatus:
    pending = pending_amount(collectible, payments)
    if not pending.is_positive():
        return PaymentStatus.PAID
    if pending == collectible:
        return PaymentStatus.PENDING
    return PaymentStatus.PARTIALLY_PAID


def warns_cash_on_reduced_works(treatment: VatTreatment, method: PaymentMethod) -> bool:
    """Aviso del RDL 29/2026 (RN-F-13): el 10 % de una obra exige pago bancario.

    Exige tarjeta, transferencia, cheque nominativo o ingreso en cuenta. Solo
    se avisa del efectivo, como dice la regla; la app no bloquea el cobro
    mientras la convalidación del real decreto-ley siga pendiente.
    """
    return treatment.rate == TaxRate.reduced() and method is PaymentMethod.CASH
