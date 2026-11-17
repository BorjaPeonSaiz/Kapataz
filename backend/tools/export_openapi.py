"""Exporta el contrato OpenAPI de la API a ``docs/api/openapi.json`` (ADR-002).

Uso, desde ``backend/``:

    uv run python tools/export_openapi.py          # escribe el fichero
    uv run python tools/export_openapi.py --check  # falla si no coincide

El frontend genera su cliente tipado a partir de ese fichero.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from kapataz.api.app import create_app
from kapataz.bootstrap import build_container
from kapataz.infrastructure.settings import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
OPENAPI_PATH = BACKEND_DIR.parent / "docs" / "api" / "openapi.json"


def build_openapi_schema() -> dict[str, Any]:
    # Configuración ficticia: el contrato no depende del entorno y el motor de
    # base de datos no se conecta hasta la primera consulta.
    settings = Settings(
        _env_file=None,
        app_env="local",
        database_url="postgresql://export:export@localhost:5432/export",
        secret_key=SecretStr("exportacion-del-contrato-openapi-sin-secretos"),  # ficticia
        git_commit="export",
    )
    container = build_container(settings)
    return create_app(settings, container.services).openapi()


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Solo comprueba; no escribe.")
    args = parser.parse_args()

    rendered = render(build_openapi_schema())
    if args.check:
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current != rendered:
            print(f"{OPENAPI_PATH} no coincide con la API. Ejecuta tools/export_openapi.py.")
            return 1
        print(f"{OPENAPI_PATH} al día.")
        return 0

    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Escrito {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
