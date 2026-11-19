"""Unidad de trabajo en memoria para las pruebas sin PostgreSQL.

Imita lo que importa de la real:

- la transacción se deshace si no hay commit;
- el email es único y el NIF de un cliente también, dentro de su cuenta;
- RLS: los repositorios de negocio exigen la cuenta fijada, no ven filas de
  otra cuenta y no escriben entidades de otra (``tenants`` igual, como su
  política);
- las claves foráneas compuestas: una factura cita un cliente y, si sale de
  un presupuesto, una versión de su cuenta;
- los triggers: una factura emitida no se toca y la cadena no se bifurca;
- los bloqueos: no bloquea nada, pero apunta en ``lock_log`` el orden en que
  se piden, para comprobar el orden de RN-F-07.

Las pruebas de integración repiten los flujos contra PostgreSQL real.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from kapataz.application.ports.persistence import AccountRepository, UnitOfWork
from kapataz.application.ports.repositories import (
    BillingChainRepository,
    CatalogRepository,
    CustomerRepository,
    InvoiceRepository,
    PaymentRepository,
    ProfessionalRepository,
    QuoteRepository,
    SeriesCounter,
    SeriesCounterRepository,
    TenantMismatchError,
    TenantNotSetError,
)
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import EmailAlreadyRegisteredError
from kapataz.domain.accounts.model import (
    EmailVerification,
    Session,
    SessionId,
    Tenant,
    TenantId,
    User,
    UserId,
)
from kapataz.domain.billing.billing_record import BillingRecord
from kapataz.domain.billing.errors import InvoiceAlreadyIssuedError, InvoiceNotFoundError
from kapataz.domain.billing.ids import (
    BillingRecordId,
    InvoiceId,
    PaymentId,
    QuoteId,
    QuoteVersionId,
)
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.numbering import Series
from kapataz.domain.billing.payment import Payment
from kapataz.domain.billing.quote import Quote, QuoteVersion
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId
from kapataz.domain.customers.errors import DuplicateCustomerTaxIdError
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.settings.professional import Professional

type CounterKey = tuple[TenantId, str, int]


@dataclass
class MemoryState:
    tenants: dict[TenantId, Tenant] = field(default_factory=dict)
    users: dict[UserId, User] = field(default_factory=dict)
    sessions: dict[SessionId, tuple[Session, str]] = field(default_factory=dict)
    verifications: dict[UUID, tuple[EmailVerification, str]] = field(default_factory=dict)
    professionals: dict[TenantId, Professional] = field(default_factory=dict)
    customers: dict[CustomerId, Customer] = field(default_factory=dict)
    catalog: dict[CatalogItemId, CatalogItem] = field(default_factory=dict)
    quotes: dict[QuoteId, Quote] = field(default_factory=dict)
    invoices: dict[InvoiceId, Invoice] = field(default_factory=dict)
    payments: dict[PaymentId, Payment] = field(default_factory=dict)
    counters: dict[CounterKey, SeriesCounter] = field(default_factory=dict)
    chain_heads: dict[TenantId, BillingRecordId | None] = field(default_factory=dict)
    billing_records: dict[BillingRecordId, BillingRecord] = field(default_factory=dict)
    # Registro anterior de cada uno, como la columna previous_record_id.
    previous_records: dict[BillingRecordId, BillingRecordId | None] = field(default_factory=dict)

    def copy(self) -> "MemoryState":
        # Las entidades son inmutables: basta con copiar los diccionarios.
        return MemoryState(
            **{name: dict(value) for name, value in vars(self).items()},
        )


class _HasTenant(Protocol):
    @property
    def tenant_id(self) -> TenantId: ...


class _Scoped:
    """Base de los repositorios de negocio: la cuenta fijada hace de RLS."""

    def __init__(self, state: MemoryState, uow: "MemoryUnitOfWork") -> None:
        self._s = state
        self._uow = uow

    @property
    def _tenant(self) -> TenantId:
        if self._uow.tenant_id is None:
            msg = "Repositorio de negocio sin cuenta fijada en la transacción."
            raise TenantNotSetError(msg)
        return self._uow.tenant_id

    def _check(self, tenant_id: TenantId) -> None:
        if tenant_id != self._tenant:
            msg = "RLS: la entidad no es de la cuenta fijada (WITH CHECK)."
            raise TenantMismatchError(msg)

    def _visible[T: _HasTenant](self, entity: T | None) -> T | None:
        if entity is None or entity.tenant_id != self._tenant:
            return None
        return entity


def _find_version(
    state: MemoryState, tenant_id: TenantId, version_id: QuoteVersionId
) -> QuoteVersion | None:
    """Versión de un presupuesto de la cuenta, como la FK compuesta y RLS."""
    for quote in state.quotes.values():
        if quote.tenant_id != tenant_id:
            continue
        for version in quote.versions:
            if version.id == version_id:
                return version
    return None


class MemoryAccounts:
    def __init__(self, state: MemoryState, uow: "MemoryUnitOfWork") -> None:
        self._s = state
        self._uow = uow

    async def add_tenant(self, tenant: Tenant) -> None:
        if self._uow.tenant_id != tenant.id:
            msg = "RLS: la cuenta fijada no coincide con la fila (WITH CHECK)."
            raise PermissionError(msg)
        self._s.tenants[tenant.id] = tenant

    async def add_user(self, user: User) -> None:
        if any(u.email == user.email for u in self._s.users.values()):
            msg = "Email ya registrado."
            raise EmailAlreadyRegisteredError(msg)
        self._s.users[user.id] = user

    async def get_user_by_email(self, email: EmailAddress) -> User | None:
        return next((u for u in self._s.users.values() if u.email == email.value), None)

    async def mark_email_verified(self, user_id: UserId, at: datetime) -> None:
        user = self._s.users[user_id]
        if user.email_verified_at is None:
            self._s.users[user_id] = replace(user, email_verified_at=at)

    async def add_email_verification(
        self, verification: EmailVerification, token_hash: str
    ) -> None:
        self._s.verifications[verification.id] = (verification, token_hash)

    async def get_email_verification_for_update(self, token_hash: str) -> EmailVerification | None:
        return next((v for v, h in self._s.verifications.values() if h == token_hash), None)

    async def mark_email_verification_used(self, verification_id: UUID, at: datetime) -> None:
        verification, token_hash = self._s.verifications[verification_id]
        self._s.verifications[verification_id] = (replace(verification, used_at=at), token_hash)

    async def add_session(self, session: Session, token_hash: str) -> None:
        self._s.sessions[session.id] = (session, token_hash)

    async def get_session_with_user(self, token_hash: str) -> tuple[Session, User] | None:
        for session, stored_hash in self._s.sessions.values():
            if stored_hash == token_hash:
                return session, self._s.users[session.user_id]
        return None

    async def touch_session(self, session_id: SessionId, at: datetime) -> None:
        session, token_hash = self._s.sessions[session_id]
        self._s.sessions[session_id] = (replace(session, last_seen_at=at), token_hash)

    async def revoke_session(self, session_id: SessionId, at: datetime) -> None:
        session, token_hash = self._s.sessions[session_id]
        if session.revoked_at is None:
            self._s.sessions[session_id] = (replace(session, revoked_at=at), token_hash)


class MemoryProfessional(_Scoped):
    async def get(self) -> Professional | None:
        return self._visible(self._s.professionals.get(self._tenant))

    async def save(self, professional: Professional) -> None:
        self._check(professional.tenant_id)
        self._s.professionals[professional.tenant_id] = professional


class MemoryCustomers(_Scoped):
    async def add(self, customer: Customer) -> None:
        self._check(customer.tenant_id)
        if customer.tax_id is not None and any(
            c.tenant_id == customer.tenant_id and c.tax_id == customer.tax_id
            for c in self._s.customers.values()
        ):
            msg = "Ya hay un cliente con ese NIF."
            raise DuplicateCustomerTaxIdError(msg)
        self._s.customers[customer.id] = customer

    async def get(self, customer_id: CustomerId) -> Customer | None:
        return self._visible(self._s.customers.get(customer_id))


class MemoryCatalog(_Scoped):
    async def add(self, item: CatalogItem) -> None:
        self._check(item.tenant_id)
        self._s.catalog[item.id] = item

    async def get(self, item_id: CatalogItemId) -> CatalogItem | None:
        return self._visible(self._s.catalog.get(item_id))


class MemoryQuotes(_Scoped):
    async def add(self, quote: Quote) -> None:
        self._check(quote.tenant_id)
        self._s.quotes[quote.id] = quote

    async def get(self, quote_id: QuoteId) -> Quote | None:
        return self._visible(self._s.quotes.get(quote_id))

    async def get_version(self, version_id: QuoteVersionId) -> QuoteVersion | None:
        return _find_version(self._s, self._tenant, version_id)

    async def save(self, quote: Quote) -> None:
        self._check(quote.tenant_id)
        self._s.quotes[quote.id] = quote


class MemoryInvoices(_Scoped):
    async def add_draft(self, invoice: Invoice) -> None:
        self._check(invoice.tenant_id)
        if invoice.is_issued:
            raise InvoiceAlreadyIssuedError("Una factura nace como borrador.")
        customer = self._s.customers.get(invoice.customer_id)
        if customer is None or customer.tenant_id != invoice.tenant_id:
            msg = "FK compuesta: el cliente no existe en la cuenta de la factura."
            raise LookupError(msg)
        if (
            invoice.quote_version_id is not None
            and _find_version(self._s, invoice.tenant_id, invoice.quote_version_id) is None
        ):
            msg = "FK compuesta: la versión del presupuesto no existe en la cuenta de la factura."
            raise LookupError(msg)
        self._s.invoices[invoice.id] = invoice

    async def get(self, invoice_id: InvoiceId) -> Invoice | None:
        return self._visible(self._s.invoices.get(invoice_id))

    async def get_for_update(self, invoice_id: InvoiceId) -> Invoice | None:
        self._uow.lock_log.append(f"invoice:{invoice_id}")
        return await self.get(invoice_id)

    async def save_draft(self, invoice: Invoice) -> None:
        self._check(invoice.tenant_id)
        if invoice.is_issued:
            raise InvoiceAlreadyIssuedError("Una factura emitida no se modifica.")
        self._require_stored_draft(invoice.id)
        self._s.invoices[invoice.id] = invoice

    async def delete_draft(self, invoice_id: InvoiceId) -> None:
        self._require_stored_draft(invoice_id)
        del self._s.invoices[invoice_id]

    async def mark_issued(self, invoice: Invoice) -> None:
        self._check(invoice.tenant_id)
        if not invoice.is_issued:
            msg = "mark_issued recibe la factura ya emitida por el dominio."
            raise ValueError(msg)
        self._require_stored_draft(invoice.id)
        self._s.invoices[invoice.id] = invoice

    def _require_stored_draft(self, invoice_id: InvoiceId) -> None:
        stored = self._visible(self._s.invoices.get(invoice_id))
        if stored is None:
            raise InvoiceNotFoundError("La factura no existe.")
        if stored.is_issued:
            # Como el trigger de RN-F-02.
            raise InvoiceAlreadyIssuedError("Una factura emitida no se modifica.")


class MemoryPayments(_Scoped):
    async def add(self, payment: Payment) -> None:
        self._check(payment.tenant_id)
        self._s.payments[payment.id] = payment

    async def list_for_invoice(self, invoice_id: InvoiceId) -> tuple[Payment, ...]:
        return tuple(
            p
            for p in self._s.payments.values()
            if p.tenant_id == self._tenant and p.invoice_id == invoice_id
        )


class MemorySeriesCounters(_Scoped):
    async def lock(self, series: Series, year: int) -> SeriesCounter:
        self._uow.lock_log.append(f"series_counter:{series}:{year}")
        key = (self._tenant, series.code, year)
        return self._s.counters.setdefault(key, SeriesCounter(series, year, None, None))

    async def last_issue_date(self, series: Series) -> date | None:
        dates = [
            counter.last_issue_date
            for (tenant_id, code, _), counter in self._s.counters.items()
            if tenant_id == self._tenant
            and code == series.code
            and counter.last_issue_date is not None
        ]
        return max(dates, default=None)

    async def save(self, counter: SeriesCounter) -> None:
        self._s.counters[(self._tenant, counter.series.code, counter.year)] = counter


class MemoryBillingChain(_Scoped):
    def __init__(self, state: MemoryState, uow: "MemoryUnitOfWork") -> None:
        super().__init__(state, uow)
        self._locked = False

    async def lock_head(self) -> BillingRecord | None:
        self._uow.lock_log.append("chain_head")
        head = self._s.chain_heads.setdefault(self._tenant, None)
        self._locked = True
        return None if head is None else self._s.billing_records[head]

    async def append(self, record: BillingRecord) -> None:
        self._check(record.tenant_id)
        if not self._locked:
            msg = "Hay que bloquear la cabeza de la cadena antes de añadir un registro."
            raise RuntimeError(msg)
        head = self._s.chain_heads[self._tenant]
        expected = None if head is None else self._s.billing_records[head].as_link()
        if record.previous != expected:
            # Como el trigger de enlace y el UNIQUE de previous_record_id.
            msg = "RN-F-07: el registro no sigue al último de la cadena."
            raise ValueError(msg)
        self._s.billing_records[record.id] = record
        self._s.previous_records[record.id] = head
        self._s.chain_heads[self._tenant] = record.id

    async def list_chain(self) -> tuple[BillingRecord, ...]:
        chain: list[BillingRecord] = []
        current = self._s.chain_heads.get(self._tenant)
        while current is not None:
            chain.append(self._s.billing_records[current])
            current = self._s.previous_records[current]
        return tuple(reversed(chain))


class MemoryUnitOfWork:
    def __init__(self, store: "MemoryUnitOfWorkFactory") -> None:
        self._store = store
        self._working = store.state.copy()
        self.tenant_id: TenantId | None = None
        self.lock_log = store.lock_log
        self._accounts = MemoryAccounts(self._working, self)
        self._professional = MemoryProfessional(self._working, self)
        self._customers = MemoryCustomers(self._working, self)
        self._catalog = MemoryCatalog(self._working, self)
        self._quotes = MemoryQuotes(self._working, self)
        self._invoices = MemoryInvoices(self._working, self)
        self._payments = MemoryPayments(self._working, self)
        self._series_counters = MemorySeriesCounters(self._working, self)
        self._billing_chain = MemoryBillingChain(self._working, self)

    @property
    def accounts(self) -> AccountRepository:
        return self._accounts

    @property
    def professional(self) -> ProfessionalRepository:
        return self._professional

    @property
    def customers(self) -> CustomerRepository:
        return self._customers

    @property
    def catalog(self) -> CatalogRepository:
        return self._catalog

    @property
    def quotes(self) -> QuoteRepository:
        return self._quotes

    @property
    def invoices(self) -> InvoiceRepository:
        return self._invoices

    @property
    def payments(self) -> PaymentRepository:
        return self._payments

    @property
    def series_counters(self) -> SeriesCounterRepository:
        return self._series_counters

    @property
    def billing_chain(self) -> BillingChainRepository:
        return self._billing_chain

    async def set_tenant(self, tenant_id: TenantId) -> None:
        self.tenant_id = tenant_id

    async def commit(self) -> None:
        self._store.state = self._working.copy()


class MemoryUnitOfWorkFactory:
    def __init__(self) -> None:
        self.state = MemoryState()
        # Orden de los bloqueos pedidos por todas las unidades de trabajo.
        self.lock_log: list[str] = []

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[UnitOfWork]:
        yield MemoryUnitOfWork(self)
