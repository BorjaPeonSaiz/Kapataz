"""Motor asíncrono de SQLAlchemy y comprobación de salud de la base de datos."""

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PING_TIMEOUT_SECONDS = 2.0
_ASYNC_DRIVER = "postgresql+asyncpg"


def to_async_url(raw_url: str) -> URL:
    """Acepta ``postgresql://``, ``postgres://`` o cualquier driver y usa asyncpg."""
    url = make_url(raw_url.replace("postgres://", "postgresql://", 1))
    if not url.drivername.startswith("postgresql"):
        msg = "Solo se admite PostgreSQL."
        raise ValueError(msg)
    return url.set(drivername=_ASYNC_DRIVER)


def create_engine(raw_url: str, **engine_options: Any) -> AsyncEngine:  # noqa: ANN401
    options: dict[str, Any] = {
        "pool_pre_ping": True,
        # Los errores de SQLAlchemy no llevan los parámetros al texto ni al log
        # (ADR-015): podrían ser emails, nombres o hashes.
        "hide_parameters": True,
        "pool_size": 5,
        "max_overflow": 5,
        "connect_args": {"server_settings": {"application_name": "kapataz"}},
    }
    options.update(engine_options)
    return create_async_engine(to_async_url(raw_url), **options)


class SqlDatabaseProbe:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def ping(self) -> bool:
        try:
            async with asyncio.timeout(PING_TIMEOUT_SECONDS), self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 - cualquier fallo es «base de datos caída» para /api/health
            return False
        return True
