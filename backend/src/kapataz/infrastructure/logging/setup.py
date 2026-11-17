"""structlog en JSON a la salida estándar, sin datos personales (ADR-015).

Es el único sitio que configura structlog. Los logs de la librería estándar
(uvicorn, SQLAlchemy, Alembic) pasan por los mismos procesadores.
"""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor

REDACTED = "[redactado]"

# Claves cuyo valor nunca se registra, aunque alguien las pase por error.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "contrasena",
        "token",
        "session",
        "cookie",
        "authorization",
        "secret",
        "secret_key",
        "api_key",
        "email",
        "to",
        "message",
        "body",
    }
)

# Segunda defensa: patrones de datos personales en cualquier texto (ADR-015).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){4,7}\b"), "[IBAN]"),
    (re.compile(r"(?<![\w-])[XYZ]?\d{7,8}[A-Z](?![\w-])", re.IGNORECASE), "[NIF]"),
    (re.compile(r"(?<![\w-])[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J](?![\w-])"), "[NIF]"),
    (re.compile(r"(?<![\w-])(?:\+34\s?)?[6789]\d{2}\s?\d{3}\s?\d{3}(?![\w-])"), "[TELEFONO]"),
)

# El evento es el nombre fijo del suceso: no se toca para no romper su búsqueda.
_UNMASKED_KEYS = frozenset({"event", "level", "timestamp", "logger", "request_id"})


def mask_text(value: str) -> str:
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def mask_personal_data(
    _logger: Any,  # noqa: ANN401 - firma de procesador de structlog
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    for key, value in list(event_dict.items()):
        if key in _UNMASKED_KEYS:
            continue
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        elif isinstance(value, str):
            event_dict[key] = mask_text(value)
    return event_dict


def _drop_color_message(
    _logger: Any,  # noqa: ANN401
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    # uvicorn duplica cada mensaje con códigos de color.
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(level: int = logging.INFO) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _drop_color_message,
        structlog.processors.format_exc_info,
        mask_personal_data,
    ]

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # httpx registra cada URL en INFO; con el SDK de Anthropic (Bloque 6) o un
    # cliente de pruebas, esas URL pueden llevar tokens.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # El log de acceso de uvicorn escribe la ruta con la query, que puede llevar
    # un token. Lo sustituye el de RequestContextMiddleware, sin query.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
