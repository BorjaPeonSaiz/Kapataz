"""Inicio de sesión con email y contraseña (RF-AC-01, ADR-025)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.ports.security import PasswordHasher
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import InvalidCredentialsError, InvalidEmailError
from kapataz.domain.accounts.model import SESSION_TTL, Session, SessionId
from kapataz.domain.accounts.tokens import hash_token, new_secret_token
from kapataz.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """El token en claro solo sale de aquí hacia la cookie ``HttpOnly``."""

    token: str
    expires_at: datetime


class LogIn:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._clock = clock
        self._dummy_hash: str | None = None

    async def execute(
        self, raw_email: str, password: str, previous_session_token: str | None = None
    ) -> IssuedSession:
        try:
            email = EmailAddress.parse(raw_email)
        except InvalidEmailError:
            await self._spend_same_time(password)
            raise InvalidCredentialsError("Credenciales incorrectas.") from None

        async with self._uow_factory() as uow:
            user = await uow.accounts.get_user_by_email(email)
            if user is None:
                await self._spend_same_time(password)
                raise InvalidCredentialsError("Credenciales incorrectas.")
            matches = await self._hasher.verify(user.password_hash, password)
            # Email sin verificar responde igual que una contraseña mala: no se
            # revela que la cuenta existe (ADR-025).
            if not matches or not user.is_verified:
                raise InvalidCredentialsError("Credenciales incorrectas.")

            now = self._clock.now()
            if previous_session_token is not None:
                # Sesión nueva en cada inicio: una cookie fijada por un atacante
                # antes del login deja de valer (fijación de sesión).
                previous = await uow.accounts.get_session_with_user(
                    hash_token(previous_session_token)
                )
                if previous is not None:
                    await uow.accounts.revoke_session(previous[0].id, now)

            token = new_secret_token()
            session = Session(
                id=SessionId(uuid4()),
                user_id=user.id,
                created_at=now,
                last_seen_at=now,
                expires_at=now + SESSION_TTL,
                revoked_at=None,
            )
            await uow.accounts.add_session(session, hash_token(token))
            await uow.commit()
        return IssuedSession(token=token, expires_at=session.expires_at)

    async def _spend_same_time(self, password: str) -> None:
        """Verifica contra un hash cualquiera para igualar el tiempo de respuesta."""
        if self._dummy_hash is None:
            self._dummy_hash = await self._hasher.hash(new_secret_token())
        await self._hasher.verify(self._dummy_hash, password)
