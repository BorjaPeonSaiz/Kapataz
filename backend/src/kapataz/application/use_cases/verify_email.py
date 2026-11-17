"""Verificación del email con un enlace de un solo uso (RF-AC-01, ADR-025)."""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.domain.accounts.errors import InvalidVerificationLinkError
from kapataz.domain.accounts.tokens import hash_token
from kapataz.domain.clock import Clock


class VerifyEmail:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, token: str) -> None:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            verification = await uow.accounts.get_email_verification_for_update(hash_token(token))
            if verification is None or not verification.is_usable(now):
                raise InvalidVerificationLinkError("Enlace no válido.")
            await uow.accounts.mark_email_verification_used(verification.id, now)
            await uow.accounts.mark_email_verified(verification.user_id, now)
            await uow.commit()
