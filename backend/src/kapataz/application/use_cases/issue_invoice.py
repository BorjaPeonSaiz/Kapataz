"""Emisión de una factura (RF-FA-02, RN-F-01, RN-F-04, RN-F-06, RN-F-07, RN-F-13; arquitectura §7).

Todo ocurre en una sola transacción. Si algo falla, se deshace entero y no se
consume ningún número, así que no quedan huecos (RN-F-01). Los bloqueos van
siempre en el mismo orden en toda operación que añade un registro de
facturación (RN-F-07):

1. la fila del borrador, para que nadie cambie sus líneas mientras se numera;
2. la cabeza de la cadena de la cuenta;
3. el contador de la serie y el año.

Las emisiones simultáneas de una cuenta esperan en la cabeza de la cadena; las
de cuentas distintas no se esperan entre sí.
"""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from kapataz.application.ports.fiscal import BillingRecordSubmissionPort
from kapataz.application.ports.persistence import UnitOfWork, UnitOfWorkFactory
from kapataz.application.ports.repositories import SeriesCounter
from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.billing_record import BillingRecord, SystemInfo, registration_record
from kapataz.domain.billing.errors import (
    InvoiceAlreadyIssuedError,
    InvoiceNotFoundError,
    MissingIssueDataError,
)
from kapataz.domain.billing.ids import BillingRecordId, InvoiceId
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.numbering import check_issue_date, next_number
from kapataz.domain.billing.party import Party, missing_issuer_data, missing_recipient_data
from kapataz.domain.billing.quote import QuoteVersion
from kapataz.domain.clock import Clock

# La fecha de expedición es la del calendario español, no la de UTC: una factura
# emitida a las 00:30 en Madrid es de ese día, aunque en UTC sea el anterior.
# Provisional: Canarias va una hora por detrás y solo cambiaría la fecha entre
# las 23:00 y las 00:00 de Canarias; pendiente del asesor fiscal y, si hace
# falta, del perfil fiscal (RF-CF-01). Decisión documentada en ADR-012.
FISCAL_TIMEZONE = ZoneInfo("Europe/Madrid")


@dataclass(frozen=True, slots=True)
class IssuedInvoice:
    """Resultado de la emisión: la factura emitida y su registro de alta."""

    invoice: Invoice
    record: BillingRecord


class IssueInvoice:
    """Convierte un borrador en una factura numerada e inmutable con su registro encadenado.

    ``system`` es el bloque SistemaInformatico de los registros (ADR-012); lo
    compone ``bootstrap.py`` con la versión de la app.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        submission: BillingRecordSubmissionPort,
        system: SystemInfo,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._submission = submission
        self._system = system

    async def execute(self, tenant_id: TenantId, invoice_id: InvoiceId) -> IssuedInvoice:
        async with self._uow_factory() as uow:
            await uow.set_tenant(tenant_id)
            draft = await uow.invoices.get_for_update(invoice_id)
            if draft is None:
                raise InvoiceNotFoundError("La factura no existe.")
            if draft.is_issued:
                raise InvoiceAlreadyIssuedError("La factura ya está emitida.")

            # 1. Cabeza de la cadena, siempre antes que el contador (RN-F-07).
            previous = await uow.billing_chain.lock_head()

            # 2. Contador de la serie y el año de la fecha de expedición (RN-F-01).
            now = self._clock.now()
            issue_date = fiscal_date(now)
            counter = await uow.series_counters.lock(draft.series, issue_date.year)

            # 3. RN-F-04 con el contador ya bloqueado.
            last_issue_date = await uow.series_counters.last_issue_date(draft.series)
            check_issue_date(issue_date, last_issue_date)

            # 4. RN-F-06, numeración sin huecos y emisión en el dominio, que
            #    copia de la versión del presupuesto el destinatario y la
            #    vivienda y comprueba con ellos el tipo de IVA (RN-F-13).
            issuer, recipient = await self._parties(uow, draft)
            quote_version = await self._quote_version(uow, draft)
            number = next_number(draft.series, issue_date.year, counter.last_number)
            issued = draft.issue(
                number=number,
                issue_date=issue_date,
                issued_at=now,
                issuer=issuer,
                recipient=recipient,
                last_issue_date=last_issue_date,
                quote_version=quote_version,
            )
            await uow.invoices.mark_issued(issued)
            await uow.series_counters.save(
                SeriesCounter(
                    series=counter.series,
                    year=counter.year,
                    last_number=number,
                    last_issue_date=issue_date,
                )
            )

            # 5. Registro de alta encadenado con el último de la cuenta (RN-F-07).
            record = registration_record(
                record_id=BillingRecordId(uuid4()),
                invoice=issued,
                previous=previous,
                system=self._system,
                generated_at=now,
            )
            await uow.billing_chain.append(record)

            # 6. Envío del registro: no hace nada hasta el Bloque 12 (ADR-012).
            await self._submission.submit(record)

            await uow.commit()
        return IssuedInvoice(invoice=issued, record=record)

    @staticmethod
    async def _parties(uow: UnitOfWork, draft: Invoice) -> tuple[Party, Party]:
        """Emisor y destinatario, o todos los datos obligatorios que faltan a la vez (RN-F-06)."""
        professional = await uow.professional.get()
        customer = await uow.customers.get(draft.customer_id)
        if customer is None:
            # Las claves foráneas compuestas impiden un borrador sin su cliente.
            msg = "El borrador cita un cliente que no existe en la cuenta."
            raise RuntimeError(msg)
        missing = (
            *draft.missing_issue_data(),
            *missing_issuer_data(professional),
            *missing_recipient_data(customer),
        )
        if missing:
            raise MissingIssueDataError(missing)
        return Party.issuer_from(professional), Party.recipient_from(customer)

    @staticmethod
    async def _quote_version(uow: UnitOfWork, draft: Invoice) -> QuoteVersion | None:
        """La versión de la que sale el borrador, o None si no sale de un presupuesto.

        No se bloquea: la versión de un presupuesto aceptado ya no cambia
        (``Quote.revise``) y la clave foránea impide borrarla mientras una
        factura la cite.
        """
        if draft.quote_version_id is None:
            return None
        version = await uow.quotes.get_version(draft.quote_version_id)
        if version is None:
            # Las claves foráneas compuestas impiden un borrador sin su versión.
            msg = "El borrador cita una versión de presupuesto que no existe en la cuenta."
            raise RuntimeError(msg)
        return version


def fiscal_date(instant: datetime) -> date:
    """Fecha de expedición que corresponde a un instante (calendario español)."""
    return instant.astimezone(FISCAL_TIMEZONE).date()
