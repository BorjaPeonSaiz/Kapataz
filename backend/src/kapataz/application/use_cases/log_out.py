"""Cierre de sesión: la sesión queda revocada en el servidor (ADR-025)."""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.domain.accounts.tokens import hash_token
from kapataz.domain.clock import Clock


class LogOut:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, session_token: str | None) -> None:
        """Idempotente: sin sesión o con una ya cerrada no hace nada."""
        if not session_token:
            return
        now = self._clock.now()
        async with self._uow_factory() as uow:
            found = await uow.accounts.get_session_with_user(hash_token(session_token))
            if found is not None and found[0].is_active(now):
                await uow.accounts.revoke_session(found[0].id, now)
                await uow.commit()
