"""Reglas de cuentas en el dominio, sin E/S."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import InvalidEmailError, WeakPasswordError
from kapataz.domain.accounts.model import (
    SESSION_TOUCH_INTERVAL,
    EmailVerification,
    Session,
    SessionId,
    Tenant,
    TenantId,
    TenantKind,
    UserId,
)
from kapataz.domain.accounts.password_policy import check_password_policy
from kapataz.domain.accounts.registration_policy import RegistrationPolicy
from kapataz.domain.accounts.tokens import hash_token, new_secret_token

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


@pytest.mark.req("RF-AC-01")
@pytest.mark.parametrize("raw", ["Ana@Ejemplo.ES", "  ana@ejemplo.es\t", "ANA@EJEMPLO.ES"])
def test_email_se_normaliza(raw):
    assert EmailAddress.parse(raw).value == "ana@ejemplo.es"


@pytest.mark.req("RF-AC-01")
@pytest.mark.parametrize("raw", ["", "ana", "ana@", "@ejemplo.es", "ana@ejemplo", "a b@c.es"])
def test_email_no_valido(raw):
    with pytest.raises(InvalidEmailError):
        EmailAddress.parse(raw)


@pytest.mark.req("RF-AC-01")
def test_email_demasiado_largo():
    with pytest.raises(InvalidEmailError):
        EmailAddress.parse("a" * 250 + "@ejemplo.es")


@pytest.mark.req("RF-AC-01")
def test_email_sin_normalizar_no_se_puede_construir():
    with pytest.raises(InvalidEmailError):
        EmailAddress("Ana@ejemplo.es")


@pytest.mark.req("RF-AC-01")
@given(st.emails())
def test_normalizar_es_idempotente(raw):
    try:
        email = EmailAddress.parse(raw)
    except InvalidEmailError:
        return
    assert EmailAddress.parse(email.value) == email


@pytest.mark.req("RF-AC-01")
@pytest.mark.parametrize("password", ["x" * 11, " " * 12, "x" * 1025, ""])
def test_contrasena_rechazada(password):
    with pytest.raises(WeakPasswordError):
        check_password_policy(password)


@pytest.mark.req("RF-AC-01")
@pytest.mark.parametrize("password", ["x" * 12, "ñ" * 12, "x" * 1024])
def test_contrasena_aceptada(password):
    check_password_policy(password)


@pytest.mark.req("RN-13")
def test_registro_cerrado_por_defecto_sin_lista():
    assert not RegistrationPolicy().allows(EmailAddress.parse("ana@ejemplo.es"))


@pytest.mark.req("RN-13")
def test_registro_cerrado_con_lista():
    policy = RegistrationPolicy(
        is_open=False, allowlist=frozenset({EmailAddress.parse("ana@ejemplo.es")})
    )
    assert policy.allows(EmailAddress.parse("ANA@ejemplo.es"))
    assert not policy.allows(EmailAddress.parse("luis@ejemplo.es"))


@pytest.mark.req("RF-AC-01")
def test_registro_abierto():
    assert RegistrationPolicy(is_open=True).allows(EmailAddress.parse("luis@ejemplo.es"))


@pytest.mark.req("RF-AC-01")
def test_tokens_aleatorios_y_hash_estable():
    first, second = new_secret_token(), new_secret_token()
    assert first != second
    assert len(first) >= 43
    assert hash_token(first) == hash_token(first)
    assert len(hash_token(first)) == 64
    assert first not in hash_token(first)


def _session(**overrides):
    values = {
        "id": SessionId(uuid4()),
        "user_id": UserId(uuid4()),
        "created_at": NOW,
        "last_seen_at": NOW,
        "expires_at": NOW + timedelta(days=14),
        "revoked_at": None,
    }
    values.update(overrides)
    return Session(**values)


@pytest.mark.req("RF-AC-01")
def test_sesion_activa_caducada_y_revocada():
    assert _session().is_active(NOW)
    assert not _session().is_active(NOW + timedelta(days=14))
    assert not _session(revoked_at=NOW).is_active(NOW)


# Sin req: solo limita las escrituras de last_seen_at; RF-AC-02 (ver las sesiones) aún no existe.
def test_sesion_solo_se_toca_cada_cierto_tiempo():
    session = _session()
    assert not session.needs_touch(NOW + SESSION_TOUCH_INTERVAL - timedelta(seconds=1))
    assert session.needs_touch(NOW + SESSION_TOUCH_INTERVAL)


@pytest.mark.req("RF-AC-01")
def test_enlace_de_verificacion_de_un_solo_uso_y_con_caducidad():
    verification = EmailVerification(
        id=uuid4(), user_id=UserId(uuid4()), expires_at=NOW + timedelta(hours=24), used_at=None
    )
    assert verification.is_usable(NOW)
    assert not verification.is_usable(NOW + timedelta(hours=24))
    used = EmailVerification(
        id=uuid4(), user_id=UserId(uuid4()), expires_at=NOW + timedelta(hours=24), used_at=NOW
    )
    assert not used.is_usable(NOW)


@pytest.mark.req("RF-CF-04")
def test_espacio_de_demostracion_exige_cuenta_padre():
    parent = TenantId(uuid4())
    Tenant(TenantId(uuid4()), "demo", TenantKind.DEMO, parent, NOW)
    Tenant(TenantId(uuid4()), "normal", TenantKind.STANDARD, None, NOW)
    with pytest.raises(ValueError, match="demostración"):
        Tenant(TenantId(uuid4()), "demo", TenantKind.DEMO, None, NOW)
    with pytest.raises(ValueError, match="demostración"):
        Tenant(TenantId(uuid4()), "normal", TenantKind.STANDARD, parent, NOW)
