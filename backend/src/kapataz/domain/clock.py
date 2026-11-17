"""Puerto Clock: única entrada del tiempo al dominio (ADR-001)."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Da la hora actual con zona horaria.

    El dominio y la aplicación nunca llaman a ``datetime.now()``: así las reglas
    que dependen de fechas (caducidades, plazos fiscales) se prueban con un
    reloj congelado.
    """

    def now(self) -> datetime:
        """Instante actual, siempre con zona horaria (UTC)."""
        ...
