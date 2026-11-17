"""Entorno de Alembic.

Las migraciones corren con el rol propietario de las tablas (``kapataz_owner``),
tomado de ``DATABASE_MIGRATION_URL``. La app usa otro rol, sin BYPASSRLS ni
propiedad de tablas (ADR-024). Las pruebas pasan una conexión ya abierta en
``config.attributes["connection"]``.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from kapataz.infrastructure.persistence.database import to_async_url
from kapataz.infrastructure.persistence.tables import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    url = os.environ.get("DATABASE_MIGRATION_URL")
    if not url:
        msg = "Falta DATABASE_MIGRATION_URL (rol propietario, kapataz_owner)."
        raise RuntimeError(msg)
    return url


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(to_async_url(_migration_url()), poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=to_async_url(_migration_url()).render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
    else:
        asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
