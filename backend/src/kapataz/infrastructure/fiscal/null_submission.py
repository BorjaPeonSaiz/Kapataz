"""NullBillingRecordSubmission: adaptador real de BillingRecordSubmissionPort hasta el Bloque 12."""

from kapataz.domain.billing.billing_record import BillingRecord


class NullBillingRecordSubmission:
    """No envía nada (ADR-012).

    El registro queda guardado con ``submission_status = pending``. El Bloque 12
    lo sustituye por ``VerifactuProviderSubmission``. No guarda los registros
    en memoria: los dobles de prueba que lo hacen viven en ``tests/fakes``.
    """

    async def submit(self, record: BillingRecord) -> None:
        del record
