"""Aislamiento entre cuentas en la base de datos (RN-10, RNF-13, ADR-024)."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import AsyncAdaptedQueuePool

from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.persistence.tables import GLOBAL_TABLES_WITHOUT_RLS
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from tests.integration.conftest import APP_ROLE, OWNER_ROLE

# Tabla de Alembic: no es de negocio y la app no tiene permisos sobre ella.
INFRASTRUCTURE_TABLES = frozenset({"alembic_version"})
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


async def _insert_tenants_as_owner(database, *ids: UUID) -> None:
    engine = database.engine(OWNER_ROLE)
    async with engine.begin() as conn:
        for tenant_id in ids:
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, name, kind, created_at) "
                    "VALUES (:id, 'prueba', 'standard', :now)"
                ),
                {"id": tenant_id, "now": NOW},
            )
    await engine.dispose()


async def _visible_tenants(database, tenant_id: UUID | None) -> set[UUID]:
    engine = database.engine(APP_ROLE)
    async with engine.begin() as conn:
        if tenant_id is not None:
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
        rows = await conn.execute(text("SELECT id FROM tenants"))
        visible = {row[0] for row in rows}
    await engine.dispose()
    return visible


@pytest.mark.req("RNF-13")
def test_toda_tabla_sin_rls_esta_en_la_lista_cerrada(database):
    async def tables_without_rls() -> set[str]:
        engine = database.engine(OWNER_ROLE)
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                    "AND NOT c.relrowsecurity"
                )
            )
            names = {row[0] for row in rows}
        await engine.dispose()
        return names

    unexpected = asyncio.run(tables_without_rls()) - GLOBAL_TABLES_WITHOUT_RLS
    unexpected -= INFRASTRUCTURE_TABLES
    assert unexpected == set(), f"Tablas sin RLS fuera de la lista cerrada: {sorted(unexpected)}"


@pytest.mark.req("RNF-13")
def test_tenants_tiene_rls_y_politica(database):
    async def check() -> tuple[bool, int]:
        engine = database.engine(OWNER_ROLE)
        async with engine.connect() as conn:
            rls = await conn.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE relname = 'tenants'")
            )
            policies = await conn.scalar(
                text("SELECT count(*) FROM pg_policies WHERE tablename = 'tenants'")
            )
        await engine.dispose()
        return bool(rls), int(policies or 0)

    assert asyncio.run(check()) == (True, 1)


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_rol_de_la_app_sin_bypassrls_ni_tablas_propias(database):
    async def check() -> tuple[bool, bool, set[str]]:
        engine = database.engine(APP_ROLE)
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
                )
            ).one()
            owned = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE tableowner = current_user")
            )
            tables = {r[0] for r in owned}
        await engine.dispose()
        return bool(row[0]), bool(row[1]), tables

    bypass, superuser, owned = asyncio.run(check())
    assert not bypass
    assert not superuser
    assert owned == set()


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_a01_rls_sin_cuenta_sin_filas(database):
    first, second = uuid4(), uuid4()
    asyncio.run(_insert_tenants_as_owner(database, first, second))

    assert asyncio.run(_visible_tenants(database, None)) == set()


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_con_cuenta_fijada_solo_se_ve_esa_cuenta(database):
    first, second = uuid4(), uuid4()
    asyncio.run(_insert_tenants_as_owner(database, first, second))

    assert asyncio.run(_visible_tenants(database, first)) == {first}
    assert asyncio.run(_visible_tenants(database, second)) == {second}


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_no_se_escribe_en_otra_cuenta(database):
    mine, other = uuid4(), uuid4()
    asyncio.run(_insert_tenants_as_owner(database, other))

    async def try_writes() -> tuple[bool, int]:
        engine = database.engine(APP_ROLE)
        insert_rejected = False
        async with engine.connect() as conn:
            await conn.begin()
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(mine)}
            )
            try:
                await conn.execute(
                    text(
                        "INSERT INTO tenants (id, name, kind, created_at) "
                        "VALUES (:id, 'intruso', 'standard', now())"
                    ),
                    {"id": other},
                )
            except DBAPIError:
                insert_rejected = True
            await conn.rollback()

            await conn.begin()
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(mine)}
            )
            updated = await conn.execute(
                text("UPDATE tenants SET name = 'robado' WHERE id = :id"), {"id": other}
            )
            await conn.rollback()
        await engine.dispose()
        return insert_rejected, updated.rowcount

    rejected, updated_rows = asyncio.run(try_writes())
    assert rejected
    assert updated_rows == 0


@pytest.mark.req("RNF-13")
def test_conexion_reutilizada_no_conserva_la_cuenta(database):
    """El pool devuelve la misma conexión: la cuenta no pasa a la transacción siguiente."""
    tenant = uuid4()
    asyncio.run(_insert_tenants_as_owner(database, tenant))

    async def scenario() -> tuple[int, str | None, int, int]:
        engine = database.engine(APP_ROLE, poolclass=AsyncAdaptedQueuePool, pool_size=1)
        factory = SqlAlchemyUnitOfWorkFactory(engine)
        async with factory() as uow:
            await uow.set_tenant(TenantId(tenant))
            pid_first = await uow._session.scalar(text("SELECT pg_backend_pid()"))
            seen_first = await uow._session.scalar(text("SELECT count(*) FROM tenants"))
            await uow.commit()
        async with factory() as uow:
            pid_second = await uow._session.scalar(text("SELECT pg_backend_pid()"))
            setting = await uow._session.scalar(
                text("SELECT current_setting('app.tenant_id', true)")
            )
            seen_second = await uow._session.scalar(text("SELECT count(*) FROM tenants"))
        await engine.dispose()
        assert pid_first == pid_second, "La prueba necesita reutilizar la misma conexión."
        return seen_first, setting, seen_second, pid_second

    seen_first, setting, seen_second, _ = asyncio.run(scenario())
    assert seen_first == 1
    assert setting in (None, "")
    assert seen_second == 0
