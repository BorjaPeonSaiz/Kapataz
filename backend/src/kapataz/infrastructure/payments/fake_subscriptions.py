"""FakeSubscriptions: toda cuenta tiene la suscripción activa hasta el Bloque 10."""

from kapataz.domain.accounts.model import TenantId


class FakeSubscriptions:
    def __init__(self) -> None:
        self._inactive: set[TenantId] = set()

    def deactivate(self, tenant_id: TenantId) -> None:
        """Para pruebas: simula una cuenta sin suscripción (RN-12)."""
        self._inactive.add(tenant_id)

    async def is_active(self, tenant_id: TenantId) -> bool:
        return tenant_id not in self._inactive
