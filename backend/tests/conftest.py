"""Configuración común de pytest."""

import os
from pathlib import Path

import pytest

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
