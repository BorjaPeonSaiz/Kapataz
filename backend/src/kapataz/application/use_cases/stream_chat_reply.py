"""Respuesta del asistente en streaming (RF-CO-01; en el Bloque 1, con FakeLlm)."""

from collections.abc import AsyncIterator

from kapataz.application.ports.llm import ChatTurn, LlmPort
from kapataz.application.ports.subscriptions import SubscriptionPort
from kapataz.domain.accounts.errors import SubscriptionInactiveError
from kapataz.domain.accounts.model import AuthenticatedUser
from kapataz.domain.errors import DomainError

MAX_CHAT_MESSAGE_LENGTH = 4000


class InvalidChatMessageError(DomainError):
    slug = "mensaje-no-valido"


class StreamChatReply:
    def __init__(self, llm: LlmPort, subscriptions: SubscriptionPort) -> None:
        self._llm = llm
        self._subscriptions = subscriptions

    async def start(self, user: AuthenticatedUser, message: str) -> AsyncIterator[str]:
        """Comprueba todo lo que puede fallar antes de abrir el stream.

        Así un error de permisos llega como respuesta HTTP normal y no como un
        evento a mitad de la conversación.
        """
        if not 1 <= len(message) <= MAX_CHAT_MESSAGE_LENGTH or not message.strip():
            msg = "El mensaje debe tener entre 1 y 4000 caracteres."
            raise InvalidChatMessageError(msg)
        if not await self._subscriptions.is_active(user.tenant_id):
            raise SubscriptionInactiveError("Suscripción inactiva.")
        return self._llm.stream_reply([ChatTurn(role="user", text=message)])
