"""Unidad de trabajo con SQLAlchemy: una transacción por caso de uso (ADR-001, ADR-024)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from kapataz.application.ports.persistence import AccountRepository, UnitOfWork
from kapataz.application.ports.repositories import (
    BillingChainRepository,
    CatalogRepository,
    CustomerRepository,
    InvoiceRepository,
    PaymentRepository,
    ProfessionalRepository,
    QuoteRepository,
    SeriesCounterRepository,
)
from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.persistence.account_repository import SqlAccountRepository
from kapataz.infrastructure.persistence.billing_chain_repository import (
    SqlBillingChainRepository,
    SqlSeriesCounterRepository,
)
from kapataz.infrastructure.persistence.invoice_repository import SqlInvoiceRepository
from kapataz.infrastructure.persistence.master_data_repositories import (
    SqlCatalogRepository,
    SqlCustomerRepository,
    SqlPaymentRepository,
    SqlProfessionalRepository,
)
from kapataz.infrastructure.persistence.quote_repository import SqlQuoteRepository
from kapataz.infrastructure.persistence.tenant_scope import TenantScope

# set_config(..., true) es SET LOCAL con parámetros: el valor vive solo hasta el
# final de la transacción, así que una conexión reutilizada del pool no arrastra
# la cuenta anterior. Las políticas RLS lo leen con current_setting.
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._scope = TenantScope()
        self._accounts = SqlAccountRepository(session)
        self._professional = SqlProfessionalRepository(session, self._scope)
        self._customers = SqlCustomerRepository(session, self._scope)
        self._catalog = SqlCatalogRepository(session, self._scope)
        self._quotes = SqlQuoteRepository(session, self._scope)
        self._invoices = SqlInvoiceRepository(session, self._scope)
        self._payments = SqlPaymentRepository(session, self._scope)
        self._series_counters = SqlSeriesCounterRepository(session, self._scope)
        self._billing_chain = SqlBillingChainRepository(session, self._scope)

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
        await self._session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
        self._scope.set(tenant_id)

    async def commit(self) -> None:
        await self._session.commit()


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[UnitOfWork]:
        # Al cerrar la sesión sin commit, SQLAlchemy hace rollback.
        async with self._sessionmaker() as session:
            yield SqlAlchemyUnitOfWork(session)
