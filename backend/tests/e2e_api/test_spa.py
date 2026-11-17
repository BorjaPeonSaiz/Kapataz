"""FastAPI sirve el build de Vue en el mismo origen (ADR-013)."""

import pytest

from tests.support import harness

# Sin req: servir la SPA es infraestructura (ADR-013). No comprueba que la PWA se pueda
# instalar (RF-MO-01); eso lo hará Playwright cuando exista el service worker (Bloque 10).

INDEX = "<!doctype html><title>Kapataz</title>"


@pytest.fixture
def static_dir(tmp_path):
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-3f9a1c2b.js").write_text("console.log('kapataz')")
    (tmp_path / "manifest.webmanifest").write_text('{"name": "Kapataz"}')
    (tmp_path / "sw.js").write_text("self.addEventListener('install', () => {})")
    return tmp_path


def test_sin_build_la_raiz_responde_404_y_la_api_funciona():
    with harness() as h:
        root = h.client.get("/")
        health = h.client.get("/api/health")

    assert root.status_code == 404
    assert root.headers["content-type"] == "application/problem+json"
    assert health.status_code == 200


@pytest.mark.parametrize("path", ["/", "/chat", "/verificar-email", "/facturas/123/editar"])
def test_rutas_de_la_spa_devuelven_index_sin_cache(static_dir, path):
    with harness(static_dir=static_dir) as h:
        response = h.client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"


def test_ficheros_con_hash_llevan_cache_larga(static_dir):
    with harness(static_dir=static_dir) as h:
        response = h.client.get("/assets/index-3f9a1c2b.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["content-type"].startswith("text/javascript")


@pytest.mark.parametrize(
    ("path", "media_type"),
    [("/manifest.webmanifest", "application/manifest+json"), ("/sw.js", "text/javascript")],
)
def test_manifiesto_y_service_worker_sin_cache(static_dir, path, media_type):
    with harness(static_dir=static_dir) as h:
        response = h.client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"].startswith(media_type)


def test_fichero_inexistente_responde_404_y_no_index(static_dir):
    with harness(static_dir=static_dir) as h:
        response = h.client.get("/assets/no-existe.js")

    assert response.status_code == 404


def test_ruta_inexistente_de_la_api_es_problem_json_y_no_index(static_dir):
    with harness(static_dir=static_dir) as h:
        response = h.client.get("/api/no-existe")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problemas/no-encontrado"


@pytest.mark.owasp("A01")
@pytest.mark.parametrize("path", ["/..%2f..%2fpyproject.toml", "/assets/..%2f..%2f..%2fREADME"])
def test_no_sale_de_la_carpeta_static(static_dir, path):
    (static_dir.parent / "pyproject.toml").write_text("secreto")
    with harness(static_dir=static_dir) as h:
        response = h.client.get(path)

    assert "secreto" not in response.text
