"""SQL directo en una sola transacción para las pruebas de los triggers de facturación.

``run_transaction`` confirma: sirve para preparar datos que la base de datos
tiene que aceptar, triggers diferidos incluidos. ``attempt`` nunca confirma:
ejecuta las sentencias, adelanta los triggers diferidos con ``SET CONSTRAINTS
ALL IMMEDIATE`` y lo deshace todo, haya fallado o no. Así un ataque que
prospere no deja datos que estropeen otras pruebas.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.integration.conftest import TestDatabase

Statement = tuple[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class Rejection:
    """Error de PostgreSQL: SQLSTATE y mensaje."""

    sqlstate: str | None
    message: str


async def _set_tenant(conn: AsyncConnection, tenant_id: UUID | None) -> None:
    if tenant_id is not None:
        await conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )


def run_transaction(
    database: TestDatabase,
    role: str,
    statements: Sequence[Statement],
    *,
    tenant_id: UUID | None = None,
) -> None:
    """Todas las sentencias en una transacción que se confirma al final."""

    async def execute() -> None:
        engine = database.engine(role)
        try:
            async with engine.begin() as conn:
                await _set_tenant(conn, tenant_id)
                for statement, params in statements:
                    await conn.execute(text(statement), dict(params))
        finally:
            await engine.dispose()

    asyncio.run(execute())


def attempt(
    database: TestDatabase,
    role: str,
    statements: Sequence[Statement],
    *,
    tenant_id: UUID | None = None,
) -> Rejection | None:
    """El primer error de las sentencias o de los triggers diferidos, o None; nunca confirma."""

    async def execute() -> Rejection | None:
        engine = database.engine(role)
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    await _set_tenant(conn, tenant_id)
                    for statement, params in (*statements, ("SET CONSTRAINTS ALL IMMEDIATE", {})):
                        await conn.execute(text(statement), dict(params))
                except DBAPIError as error:
                    return Rejection(getattr(error.orig, "sqlstate", None), str(error.orig))
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()
        return None

    return asyncio.run(execute())
