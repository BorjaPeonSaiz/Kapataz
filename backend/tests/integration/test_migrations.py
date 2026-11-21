"""Migraciones reversibles y sin desfase respecto a los modelos."""

import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kapataz.infrastructure.persistence.tables import Base
from tests.integration.conftest import OWNER_ROLE, run_alembic

# Sin req: reversibilidad y desfase de las migraciones, sin requisito propio. El aislamiento
# de RNF-13 lo comprueba test_rls.py.


async def _tables(db) -> set[str]:
    engine = db.engine(OWNER_ROLE)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        names = {row[0] for row in rows}
    await engine.dispose()
    return names


def test_upgrade_downgrade_upgrade(create_database):
    db = create_database()
    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
    assert {"tenants", "users", "sessions", "email_verifications"} <= asyncio.run(_tables(db))

    asyncio.run(run_alembic(db, lambda c: command.downgrade(c, "base")))
    assert asyncio.run(_tables(db)) <= {"alembic_version"}

    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
    assert "tenants" in asyncio.run(_tables(db))


def test_modelos_y_migraciones_coinciden(database):
    async def diff():
        engine = database.engine(OWNER_ROLE)
        async with engine.connect() as conn:
            result = await conn.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
        await engine.dispose()
        return result

    assert asyncio.run(diff()) == []


_TENANTS_STATE = """
SELECT
    (SELECT string_agg(indexname || ':' || (indexdef LIKE 'CREATE UNIQUE%')::text, ',')
       FROM pg_indexes WHERE tablename = 'tenants' AND indexdef LIKE '%(parent_tenant_id)%'),
    (SELECT count(*) FROM pg_trigger WHERE tgname = 'tenants_check_hierarchy'),
    (SELECT count(*) FROM pg_proc WHERE proname = 'tenants_check_hierarchy'),
    (SELECT string_agg(policyname, ',' ORDER BY policyname) FROM pg_policies
       WHERE tablename = 'tenants'),
    has_column_privilege('kapataz_app', 'public.tenants', 'kind', 'UPDATE'),
    has_column_privilege('kapataz_app', 'public.tenants', 'name', 'UPDATE')
"""


async def _tenants_state(db) -> tuple[object, ...]:
    engine = db.engine(OWNER_ROLE)
    async with engine.connect() as conn:
        row = (await conn.execute(text(_TENANTS_STATE))).one()
    await engine.dispose()
    return tuple(row)


@pytest.mark.req("RF-CF-04")
def test_la_0004_se_deshace_y_se_rehace(create_database):
    db = create_database()
    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
    hardened = (
        "uq_tenants_parent_tenant_id:true",
        1,
        1,
        "demo_space_from_parent,tenant_isolation",
        False,
        True,
    )
    assert asyncio.run(_tenants_state(db)) == hardened

    asyncio.run(run_alembic(db, lambda c: command.downgrade(c, "0003_facturacion")))
    assert asyncio.run(_tenants_state(db)) == (
        "ix_tenants_parent_tenant_id:false",
        0,
        0,
        "tenant_isolation",
        True,
        True,
    )

    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
    assert asyncio.run(_tenants_state(db)) == hardened


# S3-R-05: filas que la 0004 no admite, insertadas con la 0003 (sin índice
# único ni trigger). La de «sin cuenta padre» solo se puede crear quitando la
# clave foránea, que en la 0003 ya lo impide.
_DROP_PARENT_FK = "ALTER TABLE tenants DROP CONSTRAINT fk_tenants_parent_tenant_id_tenants"

_A, _D1, _D2 = (uuid4() for _ in range(3))
_BAD_ROWS = {
    "dos-espacios-en-una-cuenta": (
        False,
        [(_A, "standard", None), (_D1, "demo", _A), (_D2, "demo", _A)],
        "padre: 0; espacios dentro de otro espacio: 0; cuentas con más de un espacio: 1.",
    ),
    "espacio-dentro-de-otro": (
        False,
        [(_A, "standard", None), (_D1, "demo", _A), (_D2, "demo", _D1)],
        "padre: 0; espacios dentro de otro espacio: 1; cuentas con más de un espacio: 0.",
    ),
    "espacio-sin-cuenta-padre": (
        True,
        [(_D1, "demo", _A)],
        "padre: 1; espacios dentro de otro espacio: 0; cuentas con más de un espacio: 0.",
    ),
}


async def _owner_sql(db, *statements: tuple[str, dict[str, object]]) -> list[tuple[object, ...]]:
    engine = db.engine(OWNER_ROLE)
    rows: list[tuple[object, ...]] = []
    async with engine.begin() as conn:
        for statement, params in statements:
            result = await conn.execute(text(statement), params)
            if result.returns_rows:
                rows = [tuple(row) for row in result]
    await engine.dispose()
    return rows


_INSERT_TENANT = (
    "INSERT INTO tenants (id, name, kind, parent_tenant_id, created_at) "
    "VALUES (:id, NULL, :kind, :parent, now())"
)


def _insert_tenant(tenant_id, kind, parent) -> tuple[str, dict[str, object]]:
    return _INSERT_TENANT, {"id": tenant_id, "kind": kind, "parent": parent}


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize(("without_fk", "rows", "counts"), _BAD_ROWS.values(), ids=list(_BAD_ROWS))
def test_la_0004_no_se_aplica_si_hay_filas_que_la_incumplen(
    create_database, without_fk, rows, counts
):
    db = create_database()
    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "0003_facturacion")))
    drop_fk = [(_DROP_PARENT_FK, {})] if without_fk else []
    asyncio.run(_owner_sql(db, *drop_fk, *(_insert_tenant(*row) for row in rows)))

    with pytest.raises(DBAPIError) as failure:
        asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))

    error = failure.value.orig
    assert getattr(error, "sqlstate", None) == "KZF14"
    message = str(error)
    assert counts in message
    # Ni ids ni nombres: solo cuántas filas hay de cada caso.
    assert not any(str(tenant_id) in message for tenant_id in (_A, _D1, _D2))
    # No ha cambiado nada: sigue en la 0003, con sus filas.
    version = asyncio.run(_owner_sql(db, ("SELECT version_num FROM alembic_version", {})))
    assert version == [("0003_facturacion",)]
    assert asyncio.run(_tenants_state(db))[:3] == ("ix_tenants_parent_tenant_id:false", 0, 0)
    tenants = asyncio.run(_owner_sql(db, ("SELECT count(*) FROM tenants", {})))
    assert tenants == [(len(rows),)]

    # Corregidas las filas, se aplica.
    asyncio.run(_owner_sql(db, ("DELETE FROM tenants WHERE kind = 'demo'", {})))
    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
    assert asyncio.run(_tenants_state(db))[0] == "uq_tenants_parent_tenant_id:true"

    # La base queda como la dejan las migraciones, con su clave foránea.
    asyncio.run(run_alembic(db, lambda c: command.downgrade(c, "base")))
    asyncio.run(run_alembic(db, lambda c: command.upgrade(c, "head")))
