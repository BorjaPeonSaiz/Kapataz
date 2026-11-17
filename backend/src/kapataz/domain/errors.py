"""Errores del dominio.

Cada error lleva un ``slug`` estable. La API lo traduce a un tipo RFC 9457
(``/problemas/<slug>``) sin que el dominio sepa nada de HTTP.
"""


class DomainError(Exception):
    """Base de los errores de negocio."""

    slug: str = "error-de-dominio"
