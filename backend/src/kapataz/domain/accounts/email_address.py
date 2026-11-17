"""Objeto de valor EmailAddress, siempre normalizado."""

import re
from dataclasses import dataclass
from typing import Self

from kapataz.domain.accounts.errors import InvalidEmailError

MAX_EMAIL_LENGTH = 254

# Comprobación deliberadamente sencilla: la prueba real de que el email existe
# es el enlace de verificación (RF-AC-01), no una expresión regular.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """Email normalizado (sin espacios y en minúsculas).

    La normalización hace que ``Ana@Ejemplo.es`` y ``ana@ejemplo.es`` sean la
    misma cuenta: la columna ``users.email`` es única sobre el valor normalizado.
    """

    value: str

    def __post_init__(self) -> None:
        if self.value != _normalize(self.value) or not _is_valid(self.value):
            raise InvalidEmailError("Email no válido o sin normalizar.")

    @classmethod
    def parse(cls, raw: str) -> Self:
        normalized = _normalize(raw)
        if not _is_valid(normalized):
            raise InvalidEmailError("Email no válido.")
        return cls(normalized)

    def __str__(self) -> str:
        return self.value


def _normalize(raw: str) -> str:
    return raw.strip().lower()


def _is_valid(value: str) -> bool:
    return (
        0 < len(value) <= MAX_EMAIL_LENGTH
        and value.isprintable()
        and _EMAIL_PATTERN.fullmatch(value) is not None
    )
