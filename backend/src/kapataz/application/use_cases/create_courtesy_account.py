"""Cuenta de cortesía creada por el administrador, ya verificada (RN-13, RF-SA-04).

La usa la CLI ``kapataz-admin create-user`` para probar en producción sin SMTP.
No pasa por la política de registro: es una acción de administración.
"""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.ports.security import PasswordHasher
from kapataz.application.use_cases.account_creation import add_account
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import EmailAlreadyRegisteredError
from kapataz.domain.accounts.model import UserId
from kapataz.domain.accounts.password_policy import check_password_policy
from kapataz.domain.clock import Clock


class CreateCourtesyAccount:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, clock: Clock
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._clock = clock

    async def execute(self, raw_email: str, password: str) -> UserId:
        email = EmailAddress.parse(raw_email)
        check_password_policy(password)
        password_hash = await self._hasher.hash(password)
        async with self._uow_factory() as uow:
            if await uow.accounts.get_user_by_email(email) is not None:
                raise EmailAlreadyRegisteredError("Ese email ya tiene cuenta.")
            user_id = await add_account(
                uow, email, password_hash, now=self._clock.now(), verified=True
            )
            await uow.commit()
        return user_id
