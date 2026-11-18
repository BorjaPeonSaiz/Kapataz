"""Configuración común de pytest."""

import io
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from kapataz.infrastructure.logging.setup import configure_logging

INTEGRATION_DIR = Path(__file__).parent / "integration"
SKIP_WITHOUT_DB = (
    "TEST_DATABASE_URL no está definida: las pruebas de integración necesitan un "
    "PostgreSQL desechable. Con roles creados: TEST_DATABASE_URL (kapataz_app) y "
    "TEST_DATABASE_MIGRATION_URL (kapataz_owner). Sin ellos: TEST_DATABASE_URL con un "
    "superusuario. Detalle en tests/integration/conftest.py."
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason=SKIP_WITHOUT_DB)
    for item in items:
        if INTEGRATION_DIR in item.path.parents:
            item.add_marker(skip)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def captured_logs() -> Iterator[io.StringIO]:
    """Logs JSON de la app, tal como saldrían en producción."""
    configure_logging()
    stream = io.StringIO()
    root = logging.getLogger()
    [handler] = root.handlers
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    yield stream
    root.handlers = []
