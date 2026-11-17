"""Adaptadores falsos y de seguridad del Bloque 1."""

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from kapataz.application.ports.llm import ChatTurn, LlmUnavailableError
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.clock import FrozenClock, SystemClock
from kapataz.infrastructure.email.fake_email import FakeEmail
from kapataz.infrastructure.llm.fake_llm import DEFAULT_REPLY, FakeLlm
from kapataz.infrastructure.payments.fake_subscriptions import FakeSubscriptions
from kapataz.infrastructure.persistence.database import to_async_url
from kapataz.infrastructure.security.argon2_hasher import Argon2PasswordHasher
from kapataz.worker import run
from tests.support import fast_hasher, make_settings


async def _collect(llm: FakeLlm) -> list[str]:
    return [chunk async for chunk in llm.stream_reply([ChatTurn("user", "hola")])]


# Sin req: prueba el doble FakeLlm (ADR-008), no un requisito.
def test_fake_llm_es_determinista_y_trocea_la_respuesta():
    first = asyncio.run(_collect(FakeLlm()))
    second = asyncio.run(_collect(FakeLlm()))
    assert first == second
    assert len(first) > 1
    assert "".join(first) == DEFAULT_REPLY


# Sin req: prueba el doble FakeLlm; RNF-08 se comprueba en la API (test_health, test_chat_sse).
def test_fake_llm_simula_caida():
    llm = FakeLlm("a b c", fail_after_chunks=1)
    with pytest.raises(LlmUnavailableError):
        asyncio.run(_collect(llm))
    assert asyncio.run(FakeLlm(available=False).is_available()) is False


# Sin req: prueba el doble FakeEmail, no un requisito.
def test_fake_email_guarda_el_mensaje():
    email = FakeEmail()
    to = EmailAddress.parse("ana@ejemplo.es")
    asyncio.run(email.send_email_verification(to, "https://kapataz.test/v?token=x"))
    assert email.sent[0].to == to


# Sin req: prueba el doble FakeSubscriptions; RN-12 se comprueba en test_chat_sse.
def test_fake_subscriptions_activa_por_defecto():
    subscriptions = FakeSubscriptions()
    tenant = TenantId(uuid4())
    assert asyncio.run(subscriptions.is_active(tenant))
    subscriptions.deactivate(tenant)
    assert not asyncio.run(subscriptions.is_active(tenant))


# Sin req: prueba los relojes (Clock), infraestructura sin requisito propio.
def test_relojes():
    assert SystemClock().now().tzinfo is UTC
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FrozenClock(start)
    clock.advance(timedelta(minutes=5))
    assert clock.now() == start + timedelta(minutes=5)
    with pytest.raises(ValueError, match="zona horaria"):
        FrozenClock(datetime(2026, 1, 1))  # noqa: DTZ001


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A04")
def test_a04_password_argon2id():
    hasher = Argon2PasswordHasher()
    hashed = asyncio.run(hasher.hash("caballo-grapa-bateria"))
    assert hashed.startswith("$argon2id$")
    assert asyncio.run(hasher.verify(hashed, "caballo-grapa-bateria"))
    assert not asyncio.run(hasher.verify(hashed, "otra-cosa"))
    assert not asyncio.run(hasher.verify("no-es-un-hash", "otra-cosa"))


# Sin req: comprueba el hasher de apoyo de las pruebas, no código de la app.
def test_hasher_de_pruebas_tambien_es_argon2id():
    assert asyncio.run(fast_hasher().hash("x" * 12)).startswith("$argon2id$")


@pytest.mark.req("RN-13")
def test_configuracion_lee_la_lista_de_emails_separada_por_comas():
    settings = make_settings(
        registration_open=False, registration_allowlist="Ana@Ejemplo.es, ,luis@ejemplo.es"
    )
    assert [email.value for email in settings.registration_allowlist] == [
        "ana@ejemplo.es",
        "luis@ejemplo.es",
    ]


# Sin req: ningún requisito trata de los secretos en los errores de configuración.
def test_configuracion_no_vuelca_secretos_en_errores():
    with pytest.raises(ValueError, match="SECRET_KEY") as error:
        make_settings(secret_key="corta-y-secreta")
    assert "corta-y-secreta" not in str(error.value)


# Sin req: elección del driver de la base de datos, infraestructura sin requisito.
@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db:5432/kapataz",
        "postgres://u:p@db:5432/kapataz",
        "postgresql+psycopg://u:p@db:5432/kapataz",
    ],
)
def test_url_de_base_de_datos_usa_asyncpg(url):
    assert to_async_url(url).drivername == "postgresql+asyncpg"


# Sin req: arranque del worker; no mide la disponibilidad de RNF-03.
def test_worker_arranca_y_para_al_recibir_la_senal():
    stop = threading.Event()
    stop.set()
    run(stop)
