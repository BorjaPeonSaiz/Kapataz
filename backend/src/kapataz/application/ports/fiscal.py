"""BillingRecordSubmissionPort: envío de los registros de facturación (ADR-012, RF-VF-01)."""

from typing import Protocol

from kapataz.domain.billing.billing_record import BillingRecord


class BillingRecordSubmissionPort(Protocol):
    """Recibe cada registro nuevo de la cadena, dentro de la transacción que lo crea.

    Hasta el Bloque 12 el adaptador es ``NullBillingRecordSubmission``, que no
    hace nada. El Bloque 12 decide cómo llega a la AEAT; el envío por red no
    puede ir dentro de la transacción de emisión (HANDOFF, «Por decidir»), así
    que este método solo debe dejarlo pendiente de enviar (por ejemplo,
    encolarlo). Si lanza, la emisión entera se deshace.
    """

    async def submit(self, record: BillingRecord) -> None: ...
