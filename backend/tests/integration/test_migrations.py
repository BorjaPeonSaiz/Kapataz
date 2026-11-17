"""Migraciones reversibles y sin desfase respecto a los modelos."""

import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

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
