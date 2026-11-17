"""Inicio y cierre de sesión con cookie HttpOnly (RF-AC-01, ADR-025)."""

from datetime import timedelta

import pytest

from kapataz.api.cookies import SESSION_COOKIE
from tests.support import STRONG_PASSWORD, harness, make_settings, set_cookie_headers

EMAIL = "ana@ejemplo.es"


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_login_correcto_fija_cookie_de_sesion_con_sus_flags():
    with harness() as h:
        h.register_and_verify(EMAIL)
        response = h.log_in(EMAIL)

    assert response.status_code == 204
    [cookie] = set_cookie_headers(response, SESSION_COOKIE)
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "max-age=1209600" in lowered


@pytest.mark.req("RF-AC-01")
def test_cookie_sin_secure_si_cookie_secure_es_false():
    settings = make_settings(cookie_secure=False, public_base_url="http://localhost:8000")
    with harness(settings, base_url="http://testserver") as h:
        h.register_and_verify(EMAIL)
        response = h.log_in(EMAIL)

    [cookie] = set_cookie_headers(response, SESSION_COOKIE)
    assert "secure" not in cookie.lower()
    assert "httponly" in cookie.lower()


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
@pytest.mark.parametrize(
    ("email", "password", "verify"),
    [
        (EMAIL, "contrasena-equivocada", True),
        ("nadie@ejemplo.es", STRONG_PASSWORD, True),
        (EMAIL, STRONG_PASSWORD, False),
        ("no-es-un-email", STRONG_PASSWORD, True),
    ],
    ids=["contrasena-mala", "email-inexistente", "email-sin-verificar", "email-mal-formado"],
)
def test_login_incorrecto_responde_siempre_igual(email, password, verify):
    with harness() as h:
        if verify:
            h.register_and_verify(EMAIL)
        else:
            h.post("/api/auth/register", {"email": EMAIL, "password": STRONG_PASSWORD})
        response = h.post("/api/auth/login", {"email": email, "password": password})

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "/problemas/credenciales-incorrectas",
        "title": "Email o contraseña incorrectos.",
        "status": 401,
    }
    assert set_cookie_headers(response, SESSION_COOKIE) == []


@pytest.mark.req("RF-AC-01")
def test_me_sin_sesion_responde_401_problem():
    with harness() as h:
        response = h.client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problemas/no-autenticado"


@pytest.mark.req("RF-AC-01")
def test_me_con_cookie_inventada_responde_401():
    with harness() as h:
        h.client.cookies.set(SESSION_COOKIE, "inventada")
        assert h.client.get("/api/auth/me").status_code == 401


@pytest.mark.req("RF-AC-01")
def test_me_con_sesion_devuelve_usuario_y_cuenta():
    with harness() as h:
        h.register_and_verify(EMAIL)
        h.log_in(EMAIL)
        response = h.client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"user_id", "email", "tenant_id"}
    assert body["email"] == EMAIL


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_logout_revoca_la_sesion_en_el_servidor():
    with harness() as h:
        h.register_and_verify(EMAIL)
        h.log_in(EMAIL)
        token = h.client.cookies.get(SESSION_COOKIE)

        response = h.post("/api/auth/logout")
        assert response.status_code == 204
        [cleared] = set_cookie_headers(response, SESSION_COOKIE)
        assert "max-age=0" in cleared.lower()

        # Aunque alguien conserve la cookie, la sesión ya no vale.
        h.client.cookies.set(SESSION_COOKIE, token)
        assert h.client.get("/api/auth/me").status_code == 401


@pytest.mark.req("RF-AC-01")
def test_logout_sin_sesion_es_idempotente():
    with harness() as h:
        assert h.post("/api/auth/logout").status_code == 204


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_login_renueva_la_sesion_y_revoca_la_anterior():
    with harness() as h:
        h.register_and_verify(EMAIL)
        h.log_in(EMAIL)
        old = h.client.cookies.get(SESSION_COOKIE)
        h.log_in(EMAIL)
        new = h.client.cookies.get(SESSION_COOKIE)

        assert old != new
        h.client.cookies.set(SESSION_COOKIE, old)
        assert h.client.get("/api/auth/me").status_code == 401


@pytest.mark.req("RF-AC-01")
def test_sesion_caducada_no_autentica():
    with harness() as h:
        h.register_and_verify(EMAIL)
        h.log_in(EMAIL)
        h.clock.advance(timedelta(days=14, seconds=1))
        assert h.client.get("/api/auth/me").status_code == 401
