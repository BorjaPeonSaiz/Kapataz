"""Server-Sent Events del chat: eventos ``token``, ``done`` y ``error``."""

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from kapataz.application.ports.llm import LlmUnavailableError

SSE_MEDIA_TYPE = "text/event-stream"
# no-cache y X-Accel-Buffering: no para que ningún proxy acumule el stream (ADR-014).
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
ASSISTANT_UNAVAILABLE = "El asistente no está disponible ahora. Inténtalo más tarde."

_log = structlog.get_logger(__name__)


def format_event(event: str, data: dict[str, Any]) -> str:
    # json.dumps no emite saltos de línea, así que el campo data ocupa una sola línea.
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def chat_events(chunks: AsyncIterator[str]) -> AsyncIterator[str]:
    try:
        async for text in chunks:
            yield format_event("token", {"text": text})
    except LlmUnavailableError:
        _log.warning("llm_no_disponible")
        yield format_event("error", {"detail": ASSISTANT_UNAVAILABLE})
        return
    except Exception:  # noqa: BLE001 - se registra y se avisa con un evento error
        # El stream ya empezó con 200: el fallo solo puede llegar como evento.
        _log.exception("chat_fallido")
        yield format_event("error", {"detail": ASSISTANT_UNAVAILABLE})
        return
    yield format_event("done", {})
