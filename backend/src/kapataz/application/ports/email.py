"""EmailPort: email transaccional (verificación y, en el Bloque 10, recuperación)."""

from typing import Protocol

from kapataz.domain.accounts.email_address import EmailAddress


class EmailDeliveryError(Exception):
    """El proveedor SMTP no aceptó el mensaje."""


class EmailPort(Protocol):
    async def send_email_verification(self, to: EmailAddress, verification_url: str) -> None:
        """Envía el enlace de verificación de un solo uso (RF-AC-01)."""
        ...
