"""Registro con verificación de email (RF-AC-01, RN-13)."""

import logging
from uuid import uuid4

from kapataz.application.ports.email import EmailDeliveryError, EmailPort
from kapataz.application.ports.persistence import UnitOfWork, UnitOfWorkFactory
from kapataz.application.ports.security import PasswordHasher
from kapataz.application.use_cases.account_creation import add_account
from kapataz.application.use_cases.verification_links import VerificationLinkBuilder
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import EmailAlreadyRegisteredError, RegistrationClosedError
from kapataz.domain.accounts.model import EMAIL_VERIFICATION_TTL, EmailVerification, UserId
from kapataz.domain.accounts.password_policy import check_password_policy
from kapataz.domain.accounts.registration_policy import RegistrationPolicy
from kapataz.domain.accounts.tokens import hash_token, new_secret_token
from kapataz.domain.clock import Clock

_log = logging.getLogger(__name__)


class RegisterAccount:
    """Crea la cuenta y su usuario sin verificar y envía el enlace.

    La respuesta es la misma tanto si el email es nuevo como si ya existe, para
    no revelar qué emails tienen cuenta (ADR-025). Si ya existe sin verificar,
    se envía un enlace nuevo: así quien perdió el primero no queda bloqueado.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        email_port: EmailPort,
        clock: Clock,
        policy: RegistrationPolicy,
        links: VerificationLinkBuilder,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._email = email_port
        self._clock = clock
        self._policy = policy
        self._links = links

    async def execute(self, raw_email: str, password: str) -> None:
        email = EmailAddress.parse(raw_email)
        check_password_policy(password)
        if not self._policy.allows(email):
            raise RegistrationClosedError("El registro está cerrado.")

        # Se calcula siempre, también si el email ya existe, para que el tiempo
        # de respuesta no delate a los emails registrados.
        password_hash = await self._hasher.hash(password)

        token: str | None = None
        try:
            async with self._uow_factory() as uow:
                existing = await uow.accounts.get_user_by_email(email)
                if existing is None:
                    user_id = await add_account(
                        uow, email, password_hash, now=self._clock.now(), verified=False
                    )
                    token = await self._issue_verification(uow, user_id)
                elif not existing.is_verified:
                    token = await self._issue_verification(uow, existing.id)
                await uow.commit()
        except EmailAlreadyRegisteredError:
            # Dos registros simultáneos del mismo email: el segundo no hace nada.
            return

        if token is not None:
            try:
                await self._email.send_email_verification(
                    email, self._links.email_verification(token)
                )
            except EmailDeliveryError:
                # La cuenta queda creada; repetir el registro envía otro enlace.
                # Responder con un error revelaría que el email no estaba verificado.
                _log.warning("email_verificacion_no_enviado")

    async def _issue_verification(self, uow: UnitOfWork, user_id: UserId) -> str:
        token = new_secret_token()
        await uow.accounts.add_email_verification(
            EmailVerification(
                id=uuid4(),
                user_id=user_id,
                expires_at=self._clock.now() + EMAIL_VERIFICATION_TTL,
                used_at=None,
            ),
            hash_token(token),
        )
        return token
