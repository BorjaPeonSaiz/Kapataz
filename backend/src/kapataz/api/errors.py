"""Errores RFC 9457 (``application/problem+json``) con tipos estables ``/problemas/<slug>``.

El frontend traduce cada ``type`` con i18n: los slugs no cambian sin avisar.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from kapataz.domain.errors import DomainError

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "/problemas/"

_log = structlog.get_logger(__name__)


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """Detalle de un problema según RFC 9457."""

    model_config = ConfigDict(extra="allow")

    type: str
    title: str
    status: int
    detail: str | None = None
    errors: list[FieldError] | None = None


# slug -> (estado HTTP, título para personas)
_DOMAIN_PROBLEMS: dict[str, tuple[int, str]] = {
    "email-no-valido": (422, "El email no es válido."),
    "contrasena-debil": (422, "La contraseña debe tener al menos 12 caracteres."),
    "registro-cerrado": (403, "El registro está cerrado."),
    "credenciales-incorrectas": (401, "Email o contraseña incorrectos."),
    "enlace-no-valido": (400, "El enlace no es válido o ha caducado."),
    "no-autenticado": (401, "Tienes que iniciar sesión."),
    "suscripcion-inactiva": (403, "La suscripción no está activa."),
    "mensaje-no-valido": (422, "El mensaje no es válido."),
    "email-ya-registrado": (409, "Ese email ya tiene cuenta."),
}

_HTTP_PROBLEMS: dict[int, tuple[str, str]] = {
    400: ("peticion-no-valida", "La petición no es válida."),
    401: ("no-autenticado", "Tienes que iniciar sesión."),
    403: ("prohibido", "No tienes permiso."),
    404: ("no-encontrado", "No existe."),
    405: ("metodo-no-permitido", "Método no permitido."),
    413: ("demasiado-grande", "La petición es demasiado grande."),
    429: ("demasiadas-peticiones", "Demasiadas peticiones. Espera un poco."),
}

INTERNAL_ERROR = ("error-interno", "Algo ha fallado. Inténtalo de nuevo.")
CSRF_INVALID = ("csrf-no-valido", "La sesión del formulario ha caducado. Recarga la página.")
VALIDATION_ERROR = ("datos-no-validos", "Hay datos que no son válidos.")


def problem_body(status: int, slug: str, title: str, detail: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_PREFIX}{slug}",
        "title": title,
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    return body


def problem_response(
    status: int,
    slug: str,
    title: str,
    *,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body = problem_body(status, slug, title, detail)
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # lo garantiza el registro del manejador
        raise exc
    status, title = _DOMAIN_PROBLEMS.get(exc.slug, (400, "La petición no es válida."))
    return problem_response(status, exc.slug, title)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    slug, title = _HTTP_PROBLEMS.get(exc.status_code, ("error-http", "Error."))
    headers = dict(exc.headers) if exc.headers else None
    return problem_response(exc.status_code, slug, title, headers=headers)


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Nunca se devuelve el valor recibido: podría ser una contraseña.
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    slug, title = VALIDATION_ERROR
    return problem_response(422, slug, title, extra={"errors": errors})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)


def problem_openapi_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """Respuestas de error para el contrato OpenAPI, con ``application/problem+json``."""
    descriptions = {
        400: "Petición no válida",
        401: "Sin sesión o credenciales incorrectas",
        403: "Prohibido (csrf-no-valido, registro-cerrado o suscripcion-inactiva)",
        404: "No existe",
        422: "Datos no válidos",
    }
    return {
        status: {
            "description": descriptions.get(status, "Error"),
            "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }
