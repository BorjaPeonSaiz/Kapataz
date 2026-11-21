"""Crea el espacio de demostración de la cuenta de la sesión y lo llena de datos (RF-CF-04).

El botón «Cargar datos de ejemplo». La cuenta sale del usuario autenticado,
nunca de un id que llegue con la petición: el tipo del argumento lo impone
(S3-R-03). Una sola transacción: o se carga todo o nada.

El contenido llega ya construido con el dominio por quien llama
(``DemoContentBuilder``); este caso de uso no sabe de dónde sale. Las facturas
no entran aquí: el histórico llega como documentos importados (Bloque 4).

La carga para una cuenta elegida por id o por email es de administración y
vive aparte (``admin/``), fuera del alcance de la API, como el núcleo que
comparten las tres (``demo_space_loader``).

El núcleo entra con un alias privado y ``__all__`` solo declara
``LoadDemoSpace`` (S3-R-08). Con el nombre público, ``from
kapataz.application.use_cases.load_demo_space import load_demo_space`` le daba
a la API el núcleo con cualquier cuenta sin que ``lint-imports`` lo viera:
registra el import de este módulo, no el del núcleo. Lo impiden
``tests/security/test_api_aislamiento_estructural.py`` y mypy estricto, que no
admite reexportaciones implícitas.
"""

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.use_cases.demo_space import DemoContentBuilder, LoadedDemoSpace
from kapataz.application.use_cases.demo_space_loader import (
    load_demo_space as _load_demo_space,
)
from kapataz.domain.accounts.model import AuthenticatedUser
from kapataz.domain.clock import Clock

__all__ = ["LoadDemoSpace"]


class LoadDemoSpace:
    """Para la cuenta de la sesión."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, user: AuthenticatedUser, build: DemoContentBuilder) -> LoadedDemoSpace:
        async with self._uow_factory() as uow:
            loaded = await _load_demo_space(uow, user.tenant_id, build, now=self._clock.now())
            await uow.commit()
        return loaded
