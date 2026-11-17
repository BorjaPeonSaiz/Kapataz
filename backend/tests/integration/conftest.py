"""PostgreSQL real para las pruebas de integración.

Dos formas de configurarlo:

1. **Roles ya creados** (CI, con ``deploy/postgres-init/10-roles.sh``):
   ``TEST_DATABASE_URL`` con el rol de la app (``kapataz_app``) y
   ``TEST_DATABASE_MIGRATION_URL`` con el propietario (``kapataz_owner``), sobre
   la misma base de datos desechable. Al empezar se deja vacía (``downgrade
   base``) y se migra a la última versión.
2. **Solo un superusuario** (local, con un contenedor temporal):
   ``TEST_DATABASE_URL`` con el superusuario. Se crea una base de datos nueva
   por ejecución, los roles si faltan, y las conexiones adoptan cada rol con
   ``SET ROLE`` al conectar: RLS y permisos se evalúan contra ese rol igual que
   si iniciara sesión con él. Las bases creadas se borran al terminar.

Sin ``TEST_DATABASE_URL`` estas pruebas se saltan (``tests/conftest.py``).
"""

import asyncio
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from kapataz.infrastructure.persistence.database import to_async_url

OWNER_ROLE = "kapataz_owner"
APP_ROLE = "kapataz_app"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

_CREATE_ROLES = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{OWNER_ROLE}') THEN
        CREATE ROLE {OWNER_ROLE} NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;
"""


@dataclass(frozen=True)
class TestDatabase:
    urls: dict[str, URL]
    # True cuando se conecta como superusuario y se adopta el rol con SET ROLE.
    set_role: bool

    def engine(self, role: str, **options: Any) -> AsyncEngine:
        options.setdefault("poolclass", NullPool)
        server_settings = {"application_name": "kapataz-tests"}
        if self.set_role:
            server_settings["role"] = role
        return create_async_engine(
            self.urls[role], connect_args={"server_settings": server_settings}, **options
        )


def _alembic(connection: Connection, action: Callable[[Config], None]) -> None:
    config = Config(str(ALEMBIC_INI))
    config.attributes["connection"] = connection
    config.attributes["configure_logger"] = False
    action(config)


async def run_alembic(database: TestDatabase, action: Callable[[Config], None]) -> None:
    engine = database.engine(OWNER_ROLE)
    async with engine.begin() as connection:
        await connection.run_sync(_alembic, action)
    await engine.dispose()


def _reset_to_head(database: TestDatabase) -> None:
    asyncio.run(run_alembic(database, lambda config: command.downgrade(config, "base")))
    asyncio.run(run_alembic(database, lambda config: command.upgrade(config, "head")))


async def _admin(url: URL, *statements: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        for statement in statements:
            await connection.execute(text(statement))
    await engine.dispose()


@pytest.fixture(scope="session")
def create_database() -> Iterator[Callable[[], TestDatabase]]:
    """Devuelve una base de datos vacía, sin migrar."""
    raw_url = os.environ.get("TEST_DATABASE_URL")
    assert raw_url, "TEST_DATABASE_URL"
    raw_migration_url = os.environ.get("TEST_DATABASE_MIGRATION_URL")

    if raw_migration_url:
        fixed = TestDatabase(
            urls={APP_ROLE: to_async_url(raw_url), OWNER_ROLE: to_async_url(raw_migration_url)},
            set_role=False,
        )

        def reuse() -> TestDatabase:
            asyncio.run(run_alembic(fixed, lambda config: command.downgrade(config, "base")))
            return fixed

        yield reuse
        return

    server_url = to_async_url(raw_url)
    created: list[str] = []

    def create() -> TestDatabase:
        name = f"kapataz_test_{uuid4().hex[:10]}"
        asyncio.run(_admin(server_url, _CREATE_ROLES, f"CREATE DATABASE {name} OWNER {OWNER_ROLE}"))
        created.append(name)
        url = server_url.set(database=name)
        return TestDatabase(urls={APP_ROLE: url, OWNER_ROLE: url}, set_role=True)

    yield create
    for name in created:
        asyncio.run(_admin(server_url, f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


@pytest.fixture(scope="session")
def database(create_database: Callable[[], TestDatabase]) -> TestDatabase:
    """Base de datos compartida, vacía y migrada a la última versión."""
    db = create_database()
    _reset_to_head(db)
    return db
