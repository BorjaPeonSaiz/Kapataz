"""Adaptadores del puerto Clock."""

from datetime import UTC, datetime, timedelta


class SystemClock:
    """Único sitio del código que lee la hora del sistema (ADR-001)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Reloj fijo para pruebas; se adelanta a mano."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            msg = "FrozenClock necesita una fecha con zona horaria."
            raise ValueError(msg)
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, delta: timedelta) -> None:
        self._at += delta
