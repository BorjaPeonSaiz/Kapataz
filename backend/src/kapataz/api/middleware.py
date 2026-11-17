"""Middlewares ASGI puros: contexto de petición, cabeceras de seguridad y CSRF.

Son ASGI puros (no ``BaseHTTPMiddleware``) para no interferir con el streaming
SSE del chat.
"""

import json
import re
import time
import uuid
from collections.abc import Iterable

import structlog
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kapataz.api.csrf import CSRF_COOKIE, CSRF_HEADER, CsrfTokens
from kapataz.api.errors import CSRF_INVALID, INTERNAL_ERROR, PROBLEM_MEDIA_TYPE, problem_body

_log = structlog.get_logger("kapataz.http")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# CSP para una SPA del mismo origen, sin 'unsafe-inline' ni 'unsafe-eval'.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

# Swagger UI (solo con APP_ENV=local) carga su JS de un CDN con script en línea.
DOCS_CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    )
)

PERMISSIONS_POLICY = ", ".join(
    (
        "microphone=(self)",
        "camera=()",
        "geolocation=()",
        "payment=()",
        "usb=()",
        "serial=()",
        "bluetooth=()",
        "interest-cohort=()",
    )
)

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", PERMISSIONS_POLICY),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
)


class SecurityHeadersMiddleware:
    """Pone HSTS y las cabeceras de seguridad en toda respuesta (ADR-014, RNF-12).

    No se delega en el proxy: así no dependen de su configuración.
    """

    def __init__(self, app: ASGIApp, *, docs_paths: Iterable[str] = ()) -> None:
        self.app = app
        self._docs_paths = frozenset(docs_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        csp = DOCS_CONTENT_SECURITY_POLICY if path in self._docs_paths else CONTENT_SECURITY_POLICY
        is_api = path == "/api" or path.startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
                headers["Content-Security-Policy"] = csp
                # Las respuestas de la API llevan datos de la cuenta: nunca a caché.
                if is_api and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestContextMiddleware:
    """``request_id``, log de acceso sin query ni datos personales y error 500 en problem+json."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Request(scope).headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:  # noqa: BLE001 - se registra y se responde 500 en problem+json
            _log.exception("peticion_fallida")
            if not response_started:
                slug, title = INTERNAL_ERROR
                await _send_problem(send_with_id, 500, slug, title)
        finally:
            _log.info(
                "peticion",
                method=scope["method"],
                # Solo la ruta: la query puede llevar un token de verificación.
                path=scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )


class CsrfMiddleware:
    """Doble envío: toda mutación bajo /api exige ``X-CSRF-Token`` igual a la cookie.

    El token va firmado con ``SECRET_KEY``: alguien que pueda fijar cookies en
    el dominio no puede inventarse uno válido.
    """

    def __init__(self, app: ASGIApp, *, tokens: CsrfTokens) -> None:
        self.app = app
        self._tokens = tokens

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in _SAFE_METHODS
            and scope["path"].startswith("/api/")
        ):
            request = Request(scope)
            cookie = request.cookies.get(CSRF_COOKIE)
            header = request.headers.get(CSRF_HEADER)
            if not self._tokens.matches(cookie, header):
                slug, title = CSRF_INVALID
                await _send_problem(send, 403, slug, title)
                return
        await self.app(scope, receive, send)


async def _send_problem(send: Send, status: int, slug: str, title: str) -> None:
    body = json.dumps(problem_body(status, slug, title), ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", PROBLEM_MEDIA_TYPE.encode("ascii")),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
