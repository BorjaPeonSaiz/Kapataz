"""POST /api/chat: respuesta del asistente por SSE (RF-CO-01, RNF-04)."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from kapataz.api.dependencies import CurrentUser, Services
from kapataz.api.errors import problem_openapi_responses
from kapataz.api.schemas.chat import ChatRequest
from kapataz.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, chat_events

router = APIRouter(tags=["chat"])

_SSE_DESCRIPTION = (
    'Stream `text/event-stream` con los eventos `token` (`{"text": str}`), '
    '`done` (`{}`) al terminar y `error` (`{"detail": str}`) si el asistente falla.'
)


@router.post(
    "/chat",
    summary="Envía un mensaje al asistente y recibe la respuesta en streaming",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": _SSE_DESCRIPTION,
            "content": {SSE_MEDIA_TYPE: {"schema": {"type": "string"}}},
        },
        **problem_openapi_responses(401, 403, 422),
    },
)
async def chat(body: ChatRequest, user: CurrentUser, services: Services) -> StreamingResponse:
    chunks = await services.stream_chat_reply.start(user, body.message)
    return StreamingResponse(
        chat_events(chunks), media_type=SSE_MEDIA_TYPE, headers=dict(SSE_HEADERS)
    )
