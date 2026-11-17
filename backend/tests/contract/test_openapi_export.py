"""El contrato exportado en docs/api/openapi.json coincide con la app (ADR-002)."""

import importlib.util
import json
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "export_openapi.py"


def _tool():
    spec = importlib.util.spec_from_file_location("export_openapi", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Sin req: comprueban el contrato publicado (ADR-002), no el comportamiento de un requisito.


def test_openapi_exportado_coincide_con_la_app():
    tool = _tool()
    expected = tool.render(tool.build_openapi_schema())
    exported = tool.OPENAPI_PATH.read_text(encoding="utf-8")
    assert exported == expected, (
        "docs/api/openapi.json está desactualizado: ejecuta "
        "`uv run python tools/export_openapi.py` desde backend/."
    )


def test_contrato_publica_las_rutas_del_bloque_1():
    schema = json.loads(_tool().OPENAPI_PATH.read_text(encoding="utf-8"))
    assert set(schema["paths"]) == {
        "/api/health",
        "/api/auth/csrf",
        "/api/auth/register",
        "/api/auth/verify-email",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/chat",
    }
    assert "Problem" in schema["components"]["schemas"]
    chat_200 = schema["paths"]["/api/chat"]["post"]["responses"]["200"]
    assert set(chat_200["content"]) == {"text/event-stream"}
    login_401 = schema["paths"]["/api/auth/login"]["post"]["responses"]["401"]
    assert set(login_401["content"]) == {"application/problem+json"}
