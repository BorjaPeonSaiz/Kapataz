"""Valida la cookie de sesión y dice quién es y en qué cuenta trabaja."""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.domain.accounts.errors import NotAuthenticatedError
from kapataz.domain.accounts.model import AuthenticatedUser
from kapataz.domain.accounts.tokens import hash_token
from kapataz.domain.clock import Clock


class AuthenticateSession:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, session_token: str | None) -> AuthenticatedUser:
        if not session_token:
            raise NotAuthenticatedError("Sin sesión.")
        now = self._clock.now()
        async with self._uow_factory() as uow:
            found = await uow.accounts.get_session_with_user(hash_token(session_token))
            if found is None:
                raise NotAuthenticatedError("Sesión desconocida.")
            session, user = found
            if not session.is_active(now):
                raise NotAuthenticatedError("Sesión caducada o cerrada.")
            if session.needs_touch(now):
                await uow.accounts.touch_session(session.id, now)
                await uow.commit()
        return AuthenticatedUser(
            user_id=user.id, tenant_id=user.tenant_id, email=user.email, session_id=session.id
        )
