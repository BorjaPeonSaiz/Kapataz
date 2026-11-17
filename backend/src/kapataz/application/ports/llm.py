"""LlmPort: el modelo de lenguaje visto desde la aplicación (ADR-005, ADR-008)."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    text: str


class LlmUnavailableError(Exception):
    """El modelo no responde o devuelve un error. Lo demás sigue funcionando (RNF-08)."""


class LlmPort(Protocol):
    """Chat en streaming.

    En el Bloque 1 solo existe ``FakeLlm``. El Bloque 6 añade ``ClaudeLlm``, las
    herramientas y el tipo ``SanitizedPrompt`` (ADR-030): desde entonces el
    puerto solo aceptará texto seudonimizado.
    """

    def stream_reply(self, conversation: Sequence[ChatTurn]) -> AsyncIterator[str]:
        """Devuelve la respuesta por trozos. Lanza ``LlmUnavailableError`` si falla."""
        ...

    async def is_available(self) -> bool:
        """Comprobación barata para /api/health; nunca lanza."""
        ...
