"""FakeLlm: LLM determinista para CI, pruebas y el esqueleto del Bloque 1 (ADR-008)."""

import asyncio
import re
from collections.abc import AsyncIterator, Sequence

from kapataz.application.ports.llm import ChatTurn, LlmUnavailableError

DEFAULT_REPLY = (
    "Hola, soy el asistente de Kapataz en modo de prueba. "
    "Todavía no consulto tus datos: eso llegará en próximas versiones."
)

_WORD_CHUNK = re.compile(r"\S+\s*")


class FakeLlm:
    """Emite siempre la misma respuesta, palabra a palabra.

    ``fail_after_chunks`` simula una caída a mitad de respuesta y ``available``
    una API que no responde (RNF-08). ``received`` guarda lo que llega al
    puerto, para las pruebas de fuga del Bloque 6 (RNF-17).
    """

    def __init__(
        self,
        reply: str = DEFAULT_REPLY,
        *,
        delay_seconds: float = 0.0,
        fail_after_chunks: int | None = None,
        available: bool = True,
    ) -> None:
        self._chunks = tuple(_WORD_CHUNK.findall(reply)) or (reply,)
        self._delay = delay_seconds
        self._fail_after = fail_after_chunks
        self._available = available
        self.received: list[tuple[ChatTurn, ...]] = []

    @property
    def chunks(self) -> tuple[str, ...]:
        return self._chunks

    async def stream_reply(self, conversation: Sequence[ChatTurn]) -> AsyncIterator[str]:
        self.received.append(tuple(conversation))
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                msg = "FakeLlm: fallo simulado."
                raise LlmUnavailableError(msg)
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk

    async def is_available(self) -> bool:
        return self._available
