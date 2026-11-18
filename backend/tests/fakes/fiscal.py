"""Doble de BillingRecordSubmissionPort que apunta lo que recibe."""

from kapataz.domain.billing.billing_record import BillingRecord


class FakeBillingRecordSubmission:
    """Guarda los registros recibidos; con ``error`` lanza, para probar el rollback."""

    def __init__(self, error: Exception | None = None) -> None:
        self.submitted: list[BillingRecord] = []
        self.error = error

    async def submit(self, record: BillingRecord) -> None:
        if self.error is not None:
            raise self.error
        self.submitted.append(record)
