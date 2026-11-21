"""Administración: crea el espacio de demostración de la cuenta de un id (RF-CF-04).

Lo usa ``tools/seed_demo.py --account-id <uuid>``, que así no deja un email en
el historial de la consola. Acepta cualquier cuenta, así que no puede estar al
alcance de la API: allí la cuenta es siempre la de la sesión
(``LoadDemoSpace``, S3-R-03). Mismo núcleo, mismas reglas y misma transacción
única que ``LoadDemoSpace``.
"""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.use_cases.demo_space import DemoContentBuilder, LoadedDemoSpace
from kapataz.application.use_cases.demo_space_loader import load_demo_space
from kapataz.domain.accounts.model import TenantId
from kapataz.domain.clock import Clock


class LoadDemoSpaceForAccountId:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, tenant_id: TenantId, build: DemoContentBuilder) -> LoadedDemoSpace:
        async with self._uow_factory() as uow:
            loaded = await load_demo_space(uow, tenant_id, build, now=self._clock.now())
            await uow.commit()
        return loaded
