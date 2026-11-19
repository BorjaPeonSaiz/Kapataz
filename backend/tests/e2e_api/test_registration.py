"""Registro con verificación de email (RF-AC-01) y registro cerrado (RN-13)."""

from datetime import timedelta

import pytest

from tests.fakes.memory_uow import MemoryUnitOfWorkFactory
from tests.support import STRONG_PASSWORD, harness, make_settings


def _register(h, email: str, password: str = STRONG_PASSWORD):
    return h.post("/api/auth/register", {"email": email, "password": password})


@pytest.mark.req("RN-13")
def test_registro_cerrado_rechaza_email_no_habilitado():
    with harness(make_settings(registration_open=False)) as h:
        response = _register(h, "ana@ejemplo.es")

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problemas/registro-cerrado"
    assert h.email.sent == []


@pytest.mark.req("RN-13")
def test_registro_cerrado_admite_email_de_la_lista():
    settings = make_settings(
        registration_open=False, registration_allowlist="otro@ejemplo.es, Ana@Ejemplo.es"
    )
    with harness(settings) as h:
        response = _register(h, "  ana@EJEMPLO.es ")

    assert response.status_code == 202
    assert [str(sent.to) for sent in h.email.sent] == ["ana@ejemplo.es"]


@pytest.mark.req("RN-13")
def test_registro_cerrado_por_defecto():
    settings = make_settings()
    defaults = type(settings).model_fields["registration_open"].default
    assert defaults is False


@pytest.mark.req("RF-AC-01")
def test_registro_abierto_envia_enlace_de_verificacion():
    with harness(make_settings(registration_open=True)) as h:
        response = _register(h, "ana@ejemplo.es")

    assert response.status_code == 202
    assert response.content == b""
    [sent] = h.email.sent
    assert sent.verification_url.startswith("https://kapataz.test/verificar-email?token=")


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_email_ya_registrado_responde_igual_y_no_crea_otra_cuenta():
    with harness() as h:
        h.register_and_verify("ana@ejemplo.es")
        sent_before = len(h.email.sent)
        response = _register(h, "ANA@ejemplo.es", "otra-contrasena-cualquiera")

        assert response.status_code == 202
        assert response.content == b""
        # Cuenta ya verificada: no se manda nada nuevo ni cambia la contraseña.
        assert len(h.email.sent) == sent_before
        assert h.log_in("ana@ejemplo.es").status_code == 204


@pytest.mark.req("RF-AC-01")
def test_registro_repetido_sin_verificar_envia_enlace_nuevo():
    with harness() as h:
        _register(h, "ana@ejemplo.es")
        first = h.last_verification_token()
        _register(h, "ana@ejemplo.es")
        second = h.last_verification_token()

    assert first != second


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_contrasena_corta_se_rechaza():
    with harness() as h:
        response = _register(h, "ana@ejemplo.es", "corta-11car")

    assert response.status_code == 422
    assert response.json()["type"] == "/problemas/contrasena-debil"


@pytest.mark.req("RF-AC-01")
def test_email_no_valido_se_rechaza():
    with harness() as h:
        response = _register(h, "no-es-un-email")

    assert response.status_code == 422
    assert response.json()["type"] == "/problemas/email-no-valido"


@pytest.mark.req("RF-AC-01")
def test_errores_de_validacion_no_devuelven_lo_enviado():
    with harness() as h:
        response = h.post("/api/auth/register", {"email": "ana@ejemplo.es", "password": 7})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problemas/datos-no-validos"
    assert all("input" not in error for error in body["errors"])


@pytest.mark.req("RF-AC-01")
def test_verificacion_activa_la_cuenta_y_el_enlace_es_de_un_solo_uso():
    with harness() as h:
        _register(h, "ana@ejemplo.es")
        token = h.last_verification_token()
        assert h.log_in("ana@ejemplo.es").status_code == 401

        first = h.post("/api/auth/verify-email", {"token": token})
        second = h.post("/api/auth/verify-email", {"token": token})

        assert first.status_code == 204
        assert second.status_code == 400
        assert second.json()["type"] == "/problemas/enlace-no-valido"
        assert h.log_in("ana@ejemplo.es").status_code == 204


@pytest.mark.req("RF-AC-01")
def test_enlace_caducado_no_verifica():
    with harness() as h:
        _register(h, "ana@ejemplo.es")
        h.clock.advance(timedelta(hours=24, seconds=1))
        response = h.post("/api/auth/verify-email", {"token": h.last_verification_token()})

    assert response.status_code == 400
    assert response.json()["type"] == "/problemas/enlace-no-valido"


@pytest.mark.req("RF-AC-01")
def test_enlace_inventado_no_verifica():
    with harness() as h:
        response = h.post("/api/auth/verify-email", {"token": "inventado"})

    assert response.status_code == 400


# Un email válido de 250 caracteres: antes se copiaba en tenants.name, de 200 (F-05).
LONG_EMAIL = "a" * 64 + "@" + ("b" * 60 + ".") * 3 + "es"


@pytest.mark.req("RF-AC-01")
@pytest.mark.req("RNF-01")
def test_la_cuenta_no_copia_el_email_en_su_nombre():
    factory = MemoryUnitOfWorkFactory()
    with harness(uow_factory=factory) as h:
        h.register_and_verify(LONG_EMAIL)

    [tenant] = factory.state.tenants.values()
    assert tenant.name is None
