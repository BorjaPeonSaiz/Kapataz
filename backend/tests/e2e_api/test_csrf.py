"""Protección CSRF por doble envío firmado (ADR-025)."""

import pytest

from kapataz.api.csrf import CSRF_COOKIE, CSRF_HEADER, CsrfTokens
from tests.support import TEST_SECRET_KEY, harness, make_settings, set_cookie_headers

pytestmark = [pytest.mark.req("RF-AC-01"), pytest.mark.owasp("A01")]

LOGIN = {"email": "ana@ejemplo.es", "password": "lo-que-sea-largo"}


def test_csrf_entrega_cookie_legible_por_js():
    with harness() as h:
        response = h.client.get("/api/auth/csrf")

    assert response.status_code == 204
    [cookie] = set_cookie_headers(response, CSRF_COOKIE)
    lowered = cookie.lower()
    assert "httponly" not in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered


def test_csrf_reutiliza_el_token_vigente():
    with harness() as h:
        h.client.get("/api/auth/csrf")
        first = h.client.cookies.get(CSRF_COOKIE)
        h.client.get("/api/auth/csrf")
        assert h.client.cookies.get(CSRF_COOKIE) == first


def test_mutacion_sin_cabecera_csrf_se_rechaza():
    with harness() as h:
        h.client.get("/api/auth/csrf")
        response = h.client.post("/api/auth/login", json=LOGIN)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problemas/csrf-no-valido"


def test_mutacion_sin_cookie_csrf_se_rechaza():
    with harness() as h:
        token = CsrfTokens(TEST_SECRET_KEY).issue()
        response = h.client.post("/api/auth/login", json=LOGIN, headers={CSRF_HEADER: token})

    assert response.status_code == 403


def test_cabecera_distinta_de_la_cookie_se_rechaza():
    with harness() as h:
        h.client.get("/api/auth/csrf")
        other = CsrfTokens(TEST_SECRET_KEY).issue()
        response = h.client.post("/api/auth/login", json=LOGIN, headers={CSRF_HEADER: other})

    assert response.status_code == 403


def test_token_inventado_igual_en_cookie_y_cabecera_se_rechaza():
    """Quien fije cookies en el dominio no puede fabricar un token: va firmado."""
    forged = CsrfTokens("otra-clave-que-no-es-la-del-servidor-000000").issue()
    with harness() as h:
        h.client.cookies.set(CSRF_COOKIE, forged)
        response = h.client.post("/api/auth/login", json=LOGIN, headers={CSRF_HEADER: forged})

    assert response.status_code == 403


def test_cabecera_con_caracteres_no_ascii_se_rechaza_sin_error():
    with harness() as h:
        h.client.get("/api/auth/csrf")
        response = h.client.post("/api/auth/login", json=LOGIN, headers={CSRF_HEADER: "ñ".encode()})

    assert response.status_code == 403


def test_con_csrf_valido_la_peticion_llega_al_caso_de_uso():
    with harness() as h:
        response = h.post("/api/auth/login", LOGIN)

    assert response.status_code == 401


def test_get_no_exige_csrf():
    with harness(make_settings()) as h:
        assert h.client.get("/api/auth/me").status_code == 401
