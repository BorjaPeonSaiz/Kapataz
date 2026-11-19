"""Contadores de serie y cadena de registros de facturación (RN-F-01, RN-F-04, RN-F-07).

Los dos se bloquean con ``SELECT … FOR UPDATE`` en la transacción de la
emisión, siempre en el mismo orden: primero la cabeza de la cadena, después el
contador. Si la fila no existe todavía se crea antes con ``INSERT … ON
CONFLICT DO NOTHING``: dos transacciones que la crean a la vez no fallan, la
segunda espera a la primera y después bloquea la misma fila.
"""

import json
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from kapataz.application.ports.repositories import SeriesCounter
from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.billing_record import (
    BillingRecord,
    ChainLink,
    RecordType,
    SubmissionStatus,
    SystemInfo,
)
from kapataz.domain.billing.ids import BillingRecordId, InvoiceId
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.customers.tax_id import TaxId
from kapataz.infrastructure.persistence.tables import (
    BillingChainHeadRow,
    BillingRecordRow,
    SeriesCounterRow,
)
from kapataz.infrastructure.persistence.tenant_scope import TenantScope


class SqlSeriesCounterRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def lock(self, series: Series, year: int) -> SeriesCounter:
        tenant_id = self._scope.tenant_id
        await self._session.execute(
            pg_insert(SeriesCounterRow)
            .values(
                tenant_id=tenant_id,
                series=series.code,
                year=year,
                last_number=0,
                last_issue_date=None,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "series", "year"])
        )
        row = (
            await self._session.execute(
                select(SeriesCounterRow.last_number, SeriesCounterRow.last_issue_date)
                .where(
                    SeriesCounterRow.tenant_id == tenant_id,
                    SeriesCounterRow.series == series.code,
                    SeriesCounterRow.year == year,
                )
                .with_for_update()
            )
        ).one()
        last_number, last_issue_date = row
        return SeriesCounter(
            series=series,
            year=year,
            last_number=None if last_number == 0 else DocumentNumber(series, year, last_number),
            last_issue_date=last_issue_date,
        )

    async def last_issue_date(self, series: Series) -> date | None:
        result: date | None = await self._session.scalar(
            select(func.max(SeriesCounterRow.last_issue_date)).where(
                SeriesCounterRow.tenant_id == self._scope.tenant_id,
                SeriesCounterRow.series == series.code,
            )
        )
        return result

    async def save(self, counter: SeriesCounter) -> None:
        last = counter.last_number
        if last is not None and (last.series != counter.series or last.year != counter.year):
            msg = "El último número no es de la serie y el año del contador."
            raise ValueError(msg)
        await self._session.execute(
            update(SeriesCounterRow)
            .where(
                SeriesCounterRow.tenant_id == self._scope.tenant_id,
                SeriesCounterRow.series == counter.series.code,
                SeriesCounterRow.year == counter.year,
            )
            .values(
                last_number=0 if last is None else last.sequence,
                last_issue_date=counter.last_issue_date,
            )
        )


class SqlBillingChainRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope
        # Último registro según la cabeza bloqueada en esta transacción. None
        # dentro de la tupla es la cadena vacía; None fuera, sin bloquear.
        self._locked_head: tuple[BillingRecordId | None] | None = None

    async def lock_head(self) -> BillingRecord | None:
        tenant_id = self._scope.tenant_id
        await self._session.execute(
            pg_insert(BillingChainHeadRow)
            .values(tenant_id=tenant_id, last_record_id=None)
            .on_conflict_do_nothing(index_elements=["tenant_id"])
        )
        last_record_id = await self._session.scalar(
            select(BillingChainHeadRow.last_record_id)
            .where(BillingChainHeadRow.tenant_id == tenant_id)
            .with_for_update()
        )
        head = None if last_record_id is None else BillingRecordId(last_record_id)
        self._locked_head = (head,)
        if head is None:
            return None
        row = await self._session.scalar(
            select(BillingRecordRow).where(
                BillingRecordRow.tenant_id == tenant_id, BillingRecordRow.id == head
            )
        )
        if row is None:  # pragma: no cover - lo impide la clave foránea compuesta
            msg = "La cabeza de la cadena apunta a un registro que no existe."
            raise LookupError(msg)
        return _to_record(row)

    async def append(self, record: BillingRecord) -> None:
        self._scope.check(record.tenant_id)
        if self._locked_head is None:
            msg = "Hay que bloquear la cabeza de la cadena antes de añadir un registro (RN-F-07)."
            raise RuntimeError(msg)
        (previous_id,) = self._locked_head
        row = BillingRecordRow(**_record_values(record), previous_record_id=previous_id)
        self._session.add(row)
        await self._session.flush()
        await self._session.execute(
            update(BillingChainHeadRow)
            .where(BillingChainHeadRow.tenant_id == record.tenant_id)
            .values(last_record_id=record.id)
        )
        self._locked_head = (record.id,)

    async def list_chain(self) -> tuple[BillingRecord, ...]:
        tenant_id = self._scope.tenant_id
        head = await self._session.scalar(
            select(BillingChainHeadRow.last_record_id).where(
                BillingChainHeadRow.tenant_id == tenant_id
            )
        )
        rows = await self._session.scalars(
            select(BillingRecordRow).where(BillingRecordRow.tenant_id == tenant_id)
        )
        by_id = {row.id: row for row in rows}
        chain: list[BillingRecord] = []
        current = head
        # Se recorre desde la cabeza hacia atrás por el enlace guardado.
        while current is not None:
            row = by_id.pop(current)
            chain.append(_to_record(row))
            current = row.previous_record_id
        chain.reverse()
        return tuple(chain)


def _record_values(record: BillingRecord) -> dict[str, object]:
    previous = record.previous
    system = record.system
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "invoice_id": record.invoice_id,
        "record_type": record.record_type.value,
        "is_correction": record.is_correction,
        "prior_rejection": record.prior_rejection,
        "issuer_tax_id": str(record.issuer_tax_id),
        "series_number": record.series_number,
        "issue_date": record.issue_date,
        "is_first": record.is_first,
        "prev_issuer_tax_id": None if previous is None else str(previous.issuer_tax_id),
        "prev_series_number": None if previous is None else previous.series_number,
        "prev_issue_date": None if previous is None else previous.issue_date,
        "prev_hash": None if previous is None else previous.hash,
        "system_name": system.system_name,
        "system_id": system.system_id,
        "system_version": system.version,
        "installation_number": system.installation_number,
        "generated_at": record.generated_at,
        "external_ref": record.external_ref,
        # Tal como lo produce el dominio: la persistencia no recalcula nada.
        "canonical_json": record.canonical_json,
        "hash": record.hash,
        "submission_status": record.submission_status.value,
        "error_code": record.error_code,
        "error_description": record.error_description,
        "submission_csv": record.submission_csv,
        "submitted_at": record.submitted_at,
        "sent_with_incident": record.sent_with_incident,
    }


def _to_record(row: BillingRecordRow) -> BillingRecord:
    """Reconstruye el registro. El dominio comprueba al construirlo que la huella cuadra."""
    content = json.loads(row.canonical_json)
    return BillingRecord(
        id=BillingRecordId(row.id),
        tenant_id=TenantId(row.tenant_id),
        invoice_id=InvoiceId(row.invoice_id),
        record_type=RecordType(row.record_type),
        is_correction=row.is_correction,
        prior_rejection=row.prior_rejection,
        issuer_tax_id=TaxId(row.issuer_tax_id),
        series_number=row.series_number,
        issue_date=row.issue_date,
        previous=_link(row),
        system=SystemInfo.from_canonical(content.get("SistemaInformatico")),
        generated_at=row.generated_at,
        external_ref=row.external_ref,
        canonical_json=row.canonical_json,
        hash=row.hash,
        submission_status=SubmissionStatus(row.submission_status),
        error_code=row.error_code,
        error_description=row.error_description,
        submission_csv=row.submission_csv,
        submitted_at=row.submitted_at,
        sent_with_incident=row.sent_with_incident,
    )


def _link(row: BillingRecordRow) -> ChainLink | None:
    if row.is_first:
        return None
    if (
        row.prev_issuer_tax_id is None
        or row.prev_series_number is None
        or row.prev_issue_date is None
        or row.prev_hash is None
    ):  # pragma: no cover - lo impide la restricción chain_link
        msg = "Registro encadenado sin los datos del anterior."
        raise ValueError(msg)
    return ChainLink(
        issuer_tax_id=TaxId(row.prev_issuer_tax_id),
        series_number=row.prev_series_number,
        issue_date=row.prev_issue_date,
        hash=row.prev_hash,
    )
