"""Construcción de la aplicación FastAPI a partir de casos de uso ya compuestos."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi

from kapataz.api.csrf import CsrfTokens
from kapataz.api.errors import FieldError, Problem, install_error_handlers
from kapataz.api.middleware import (
    CsrfMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from kapataz.api.routers import auth, chat, health
from kapataz.api.spa import DEFAULT_STATIC_DIR, install_spa
from kapataz.application.services import AppServices
from kapataz.infrastructure.settings import Settings

API_TITLE = "Kapataz API"
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
_DOCS_PATHS = frozenset({DOCS_URL, f"{DOCS_URL}/oauth2-redirect", "/redoc", OPENAPI_URL})


async def _nothing() -> None:
    return None


def create_app(
    settings: Settings,
    services: AppServices,
    *,
    on_shutdown: Callable[[], Awaitable[None]] = _nothing,
    static_dir: Path = DEFAULT_STATIC_DIR,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await on_shutdown()

    # En producción no se publica la documentación interactiva ni el esquema.
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=API_TITLE,
        version=version("kapataz"),
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        openapi_url=OPENAPI_URL if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    app.state.csrf_tokens = CsrfTokens(settings.secret_key.get_secret_value())

    install_error_handlers(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(chat.router)
    app.include_router(api)

    install_spa(app, static_dir, reserved_paths=frozenset(p.lstrip("/") for p in _DOCS_PATHS))

    # El último que se añade es el más externo: cabeceras > contexto > CSRF.
    app.add_middleware(CsrfMiddleware, tokens=app.state.csrf_tokens)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware, docs_paths=_DOCS_PATHS if docs_enabled else frozenset()
    )

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            schemas = schema.setdefault("components", {}).setdefault("schemas", {})
            schemas["FieldError"] = FieldError.model_json_schema()
            problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
            problem.pop("$defs", None)
            schemas["Problem"] = problem
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app
