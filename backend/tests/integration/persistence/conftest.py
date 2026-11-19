"""Utilidades de las pruebas de persistencia de facturación contra PostgreSQL real.

Cada prueba crea sus propias cuentas: comparten la base de datos de la sesión
(``database``) sin pisarse.
"""

import asyncio
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from kapataz.application.use_cases.issue_invoice import IssuedInvoice, IssueInvoice
from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.clock import FrozenClock
from kapataz.infrastructure.fiscal.null_submission import NullBillingRecordSubmission
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from tests.billing_support import SYSTEM, issuable_drafts
from tests.integration.conftest import APP_ROLE, TestDatabase

ISSUE_AT = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)


@pytest.fixture
def app_factory(database: TestDatabase) -> Iterator[SqlAlchemyUnitOfWorkFactory]:
    """Unidad de trabajo real con el rol de la app (sin BYPASSRLS)."""
    engine = database.engine(APP_ROLE)
    yield SqlAlchemyUnitOfWorkFactory(engine)
    asyncio.run(engine.dispose())


def issue_use_case(factory: SqlAlchemyUnitOfWorkFactory, at: datetime = ISSUE_AT) -> IssueInvoice:
    return IssueInvoice(factory, FrozenClock(at), NullBillingRecordSubmission(), SYSTEM)


def issue_new(
    factory: SqlAlchemyUnitOfWorkFactory, count: int = 1
) -> tuple[TenantId, list[IssuedInvoice]]:
    """Cuenta nueva con ``count`` facturas emitidas por el caso de uso."""
    tenant_id, drafts = asyncio.run(issuable_drafts(factory, count))
    use_case = issue_use_case(factory)
    return tenant_id, [asyncio.run(use_case.execute(tenant_id, draft)) for draft in drafts]


def run_sql(
    database: TestDatabase,
    role: str,
    statement: str,
    params: Mapping[str, Any] | None = None,
    *,
    tenant_id: UUID | None = None,
) -> list[Any]:
    """Una sentencia en su propia transacción, con ese rol y, si se da, la cuenta fijada."""

    async def execute() -> list[Any]:
        engine = database.engine(role)
        try:
            async with engine.begin() as conn:
                if tenant_id is not None:
                    await conn.execute(
                        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
                    )
                result = await conn.execute(text(statement), dict(params or {}))
                return list(result.all()) if result.returns_rows else []
        finally:
            await engine.dispose()

    return asyncio.run(execute())
