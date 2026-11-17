"""Unidad de trabajo con SQLAlchemy: una transacción por caso de uso (ADR-001, ADR-024)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from kapataz.application.ports.persistence import AccountRepository, UnitOfWork
from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.persistence.account_repository import SqlAccountRepository

# set_config(..., true) es SET LOCAL con parámetros: el valor vive solo hasta el
# final de la transacción, así que una conexión reutilizada del pool no arrastra
# la cuenta anterior. Las políticas RLS lo leen con current_setting.
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._accounts = SqlAccountRepository(session)

    @property
    def accounts(self) -> AccountRepository:
        return self._accounts

    async def set_tenant(self, tenant_id: TenantId) -> None:
        await self._session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})

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
