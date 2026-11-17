"""SmtpEmail: envío por SMTP transaccional con un proveedor de la UE."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from kapataz.application.ports.email import EmailDeliveryError
from kapataz.domain.accounts.email_address import EmailAddress

SMTPS_PORT = 465
SMTP_TIMEOUT_SECONDS = 15


class SmtpEmail:
    """SMTPS en el puerto 465; STARTTLS obligatorio en cualquier otro."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._user = user
        self._password = password

    async def send_email_verification(self, to: EmailAddress, verification_url: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to.value
        message["Subject"] = "Confirma tu email en Kapataz"
        message.set_content(
            "Hola:\n\n"
            "Para activar tu cuenta de Kapataz, abre este enlace:\n\n"
            f"{verification_url}\n\n"
            "El enlace caduca en 24 horas y solo sirve una vez.\n"
            "Si no has pedido una cuenta, ignora este mensaje.\n"
        )
        await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        try:
            if self._port == SMTPS_PORT:
                with smtplib.SMTP_SSL(
                    self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS, context=context
                ) as client:
                    self._login_and_send(client, message)
            else:
                with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as client:
                    client.starttls(context=context)
                    self._login_and_send(client, message)
        except (smtplib.SMTPException, OSError) as error:
            msg = "El servidor SMTP no aceptó el mensaje."
            raise EmailDeliveryError(msg) from error

    def _login_and_send(self, client: smtplib.SMTP, message: EmailMessage) -> None:
        if self._user and self._password:
            client.login(self._user, self._password)
        client.send_message(message)
