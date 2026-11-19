"""Los logs no llevan emails, contraseñas ni tokens (ADR-015, RNF-01)."""

import json

import pytest

from kapataz.api.cookies import SESSION_COOKIE
from kapataz.infrastructure.logging.setup import (
    REDACTED,
    mask_personal_data,
    mask_text,
)
from tests.support import STRONG_PASSWORD, harness

# A09 en todo el módulo (plan de verificación, Fase 7). RNF-01 en las que comprueban que no
# quedan datos personales (ADR-015); las otras dos comprueban qué sí debe quedar en el log.
pytestmark = pytest.mark.owasp("A09")


@pytest.mark.req("RNF-01")
def test_flujo_de_cuenta_no_deja_datos_personales_en_logs(captured_logs):
    email = "maria.garcia@ejemplo.es"
    with harness() as h:
        h.register_and_verify(email)
        verification_token = h.last_verification_token()
        h.log_in(email)
        session_token = h.client.cookies.get(SESSION_COOKIE)
        h.client.get(f"/verificar-email?token={verification_token}")
        h.post("/api/chat", {"message": "Mi DNI es 12345678Z"})

    output = captured_logs.getvalue()
    lines = [json.loads(line) for line in output.splitlines() if line.strip()]
    assert any(line["event"] == "peticion" for line in lines)
    assert all("request_id" in line for line in lines if line["event"] == "peticion")
    for secret in (email, STRONG_PASSWORD, verification_token, session_token, "12345678Z"):
        assert secret not in output


def test_log_de_peticion_lleva_la_cuenta_tras_autenticar(captured_logs):
    with harness() as h:
        h.register_and_verify("ana@ejemplo.es")
        h.log_in("ana@ejemplo.es")
        tenant_id = h.client.get("/api/auth/me").json()["tenant_id"]

    lines = [json.loads(line) for line in captured_logs.getvalue().splitlines() if line.strip()]
    me_lines = [line for line in lines if line.get("path") == "/api/auth/me"]
    assert me_lines[-1]["tenant_id"] == tenant_id


@pytest.mark.req("RNF-01")
@pytest.mark.parametrize(
    ("text", "replacement"),
    [
        ("escribe a ana.lopez+obra@ejemplo.es mañana", "[EMAIL]"),
        ("NIF 12345678Z del cliente", "[NIF]"),
        ("NIE X1234567L", "[NIF]"),
        ("CIF B12345678", "[NIF]"),
        ("IBAN ES9121000418450200051332", "[IBAN]"),
        ("llama al 612 345 678", "[TELEFONO]"),
        ("llama al +34 912345678", "[TELEFONO]"),
    ],
)
def test_enmascarado_de_patrones(text, replacement):
    masked = mask_text(text)
    assert replacement in masked


def test_enmascarado_no_toca_identificadores():
    request_id = "3f9a1c2b4d5e6f708192a3b4c5d6e7f8"
    uuid = "0b6f1d2e-3c4a-4b5c-8d9e-0f1a2b3c4d5e"
    assert mask_text(f"{request_id} {uuid}") == f"{request_id} {uuid}"


@pytest.mark.req("RNF-01")
def test_claves_sensibles_se_redactan():
    event = mask_personal_data(
        None, "info", {"event": "x", "password": "p", "email": "e", "token": "t", "status": 200}
    )
    assert event == {
        "event": "x",
        "password": REDACTED,
        "email": REDACTED,
        "token": REDACTED,
        "status": 200,
    }
