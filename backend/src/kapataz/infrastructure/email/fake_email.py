"""FakeEmail: guarda los mensajes en memoria en lugar de enviarlos."""

from dataclasses import dataclass

import structlog

from kapataz.domain.accounts.email_address import EmailAddress

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SentVerificationEmail:
    to: EmailAddress
    verification_url: str


class FakeEmail:
    def __init__(self) -> None:
        self.sent: list[SentVerificationEmail] = []

    async def send_email_verification(self, to: EmailAddress, verification_url: str) -> None:
        self.sent.append(SentVerificationEmail(to=to, verification_url=verification_url))
        # Ni el destinatario ni el enlace van al log (ADR-015).
        _log.info("email_no_enviado", reason="EMAIL_BACKEND=fake", kind="email_verification")
