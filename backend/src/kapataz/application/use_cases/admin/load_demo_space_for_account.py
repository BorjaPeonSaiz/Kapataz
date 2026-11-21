"""Administración: crea el espacio de demostración de la cuenta de un email (RF-CF-04).

Lo usa ``tools/seed_demo.py --account <email>``. Elige la cuenta por el email
de su usuario, así que no puede estar al alcance de la API: allí la cuenta es
siempre la de la sesión (``LoadDemoSpace``). Mismo núcleo, mismas reglas y
misma transacción única que ``LoadDemoSpace``.
"""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.use_cases.demo_space import DemoContentBuilder, LoadedDemoSpace
from kapataz.application.use_cases.demo_space_loader import load_demo_space
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import AccountNotFoundError
from kapataz.domain.clock import Clock


class LoadDemoSpaceForAccount:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, raw_email: str, build: DemoContentBuilder) -> LoadedDemoSpace:
        email = EmailAddress.parse(raw_email)
        async with self._uow_factory() as uow:
            user = await uow.accounts.get_user_by_email(email)
            if user is None:
                raise AccountNotFoundError("No hay ninguna cuenta con ese email.")
            loaded = await load_demo_space(uow, user.tenant_id, build, now=self._clock.now())
            await uow.commit()
        return loaded
