"""SubscriptionPort: estado de la suscripción de una cuenta (ADR-016)."""

from typing import Protocol

from kapataz.domain.accounts.model import TenantId


class SubscriptionPort(Protocol):
    async def is_active(self, tenant_id: TenantId) -> bool:
        """Sin suscripción activa la cuenta queda en solo lectura y sin IA (RN-12).

        El estado solo lo cambia un webhook de Stripe verificado, nunca el
        navegador. Hasta el Bloque 10 se usa ``FakeSubscriptions``.
        """
        ...
