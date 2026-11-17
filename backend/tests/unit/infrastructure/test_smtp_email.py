"""SmtpEmail: TLS obligatorio y fallos del proveedor tratados (RF-AC-01)."""

import asyncio
import smtplib

import pytest

from kapataz.application.ports.email import EmailDeliveryError
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.infrastructure.email import smtp_email
from kapataz.infrastructure.email.smtp_email import SmtpEmail
from tests.support import harness

TO = EmailAddress.parse("ana@ejemplo.es")
LINK = "https://kapataz.test/verificar-email?token=abc"


class RecordingSmtp:
    instances: list["RecordingSmtp"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent = []
        RecordingSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(f"login:{user}")

    def send_message(self, message):
        self.calls.append("send")
        self.sent.append(message)


@pytest.fixture
def smtp(monkeypatch):
    RecordingSmtp.instances = []
    monkeypatch.setattr(smtp_email.smtplib, "SMTP", RecordingSmtp)
    monkeypatch.setattr(smtp_email.smtplib, "SMTP_SSL", RecordingSmtp)
    return RecordingSmtp


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A04")
def test_puerto_587_usa_starttls_antes_de_autenticarse(smtp):
    email = SmtpEmail("smtp.ejemplo.eu", 587, "Kapataz <no-responder@kapataz.es>", "u", "p")
    asyncio.run(email.send_email_verification(TO, LINK))

    [client] = smtp.instances
    assert client.calls == ["starttls", "login:u", "send"]
    [message] = client.sent
    assert message["To"] == "ana@ejemplo.es"
    assert LINK in message.get_content()


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A04")
def test_puerto_465_usa_smtps(smtp):
    email = SmtpEmail("smtp.ejemplo.eu", 465, "no-responder@kapataz.es")
    asyncio.run(email.send_email_verification(TO, LINK))

    [client] = smtp.instances
    assert client.calls == ["send"]


@pytest.mark.req("RF-AC-01")
def test_fallo_del_proveedor_se_convierte_en_error_del_puerto(monkeypatch):
    def broken(*args, **kwargs):
        raise smtplib.SMTPConnectError(421, b"no")

    monkeypatch.setattr(smtp_email.smtplib, "SMTP", broken)
    email = SmtpEmail("smtp.ejemplo.eu", 587, "no-responder@kapataz.es")
    with pytest.raises(EmailDeliveryError):
        asyncio.run(email.send_email_verification(TO, LINK))


class FailingEmail:
    async def send_email_verification(self, to, verification_url):
        raise EmailDeliveryError("caído")


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_registro_responde_202_aunque_falle_el_email():
    """Un 5xx revelaría que el email no tenía cuenta verificada."""
    with harness(email_port=FailingEmail()) as h:
        response = h.post("/api/auth/register", {"email": "ana@ejemplo.es", "password": "x" * 16})

    assert response.status_code == 202
