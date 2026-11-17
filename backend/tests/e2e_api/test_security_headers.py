"""Cabeceras de seguridad en toda respuesta, sin proxy delante (ADR-014, RNF-12)."""

import pytest

from tests.support import StubDatabaseProbe, harness, make_settings

# A02 (configuración de seguridad incorrecta) en todo el módulo. RNF-12 solo en las pruebas que
# comprueban HSTS o que se exige HTTPS; las demás (caché, CORS, request id, /docs) no tienen
# requisito propio.
pytestmark = pytest.mark.owasp("A02")

EXPECTED = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


def _assert_security_headers(response) -> None:
    for name, value in EXPECTED.items():
        assert response.headers.get(name) == value, name
    csp = response.headers["content-security-policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "microphone=(self)" in response.headers["permissions-policy"]


@pytest.mark.req("RNF-12")
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/health"),
        ("GET", "/api/auth/csrf"),
        ("GET", "/api/auth/me"),
        ("GET", "/api/no-existe"),
        ("POST", "/api/auth/login"),
        ("GET", "/"),
        ("GET", "/chat"),
    ],
)
def test_toda_respuesta_lleva_las_cabeceras(method, path):
    with harness() as h:
        response = h.client.request(method, path)

    _assert_security_headers(response)


@pytest.mark.req("RNF-12")
def test_error_500_tambien_lleva_cabeceras_y_es_problem_json():
    probe = StubDatabaseProbe(error=RuntimeError("fallo inesperado"))
    with harness(database_probe=probe) as h:
        response = h.client.get("/api/health")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problemas/error-interno"
    assert "fallo inesperado" not in response.text
    _assert_security_headers(response)


@pytest.mark.req("RNF-12")
def test_sse_lleva_las_cabeceras():
    with harness() as h:
        h.register_and_verify("ana@ejemplo.es")
        h.log_in("ana@ejemplo.es")
        response = h.post("/api/chat", {"message": "hola"})

    _assert_security_headers(response)


def test_api_no_se_guarda_en_cache():
    with harness() as h:
        assert h.client.get("/api/auth/me").headers["cache-control"] == "no-store"
        assert h.client.get("/api/health").headers["cache-control"] == "no-store"


def test_sin_cors():
    """Mismo origen: la API no anuncia CORS a otros orígenes (ADR-013)."""
    with harness() as h:
        response = h.client.get("/api/health", headers={"Origin": "https://malo.example"})
        preflight = h.client.options(
            "/api/auth/login",
            headers={"Origin": "https://malo.example", "Access-Control-Request-Method": "POST"},
        )

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in preflight.headers


def test_request_id_en_la_respuesta():
    with harness() as h:
        generated = h.client.get("/api/health").headers["x-request-id"]
        echoed = h.client.get("/api/health", headers={"X-Request-ID": "peticion-1234"})
        rejected = h.client.get("/api/health", headers={"X-Request-ID": "<script>"})

    assert len(generated) == 32
    assert echoed.headers["x-request-id"] == "peticion-1234"
    assert rejected.headers["x-request-id"] != "<script>"


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
def test_docs_desactivado_en_produccion(path, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Kapataz</title>")
    settings = make_settings(app_env="production")
    with harness(settings, static_dir=tmp_path) as h:
        response = h.client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_docs_disponible_en_local():
    with harness(make_settings(app_env="local")) as h:
        docs = h.client.get("/docs")
        schema = h.client.get("/openapi.json")

    assert docs.status_code == 200
    assert schema.status_code == 200
    # Swagger UI necesita su propia CSP, solo en local.
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]


@pytest.mark.req("RNF-12")
def test_produccion_exige_cookie_secure_y_https():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        make_settings(app_env="production", cookie_secure=False)
    with pytest.raises(ValueError, match="https"):
        make_settings(app_env="production", public_base_url="http://kapataz.kodigolab.es")
