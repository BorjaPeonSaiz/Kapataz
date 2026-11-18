"""Repositorio de presupuestos con sus versiones y líneas (RF-PR-01 a RF-PR-07)."""

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.ids import QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.quote import (
    PriceSource,
    PriceSourceKind,
    Quote,
    QuoteLine,
    QuoteStatus,
    QuoteVersion,
)
from kapataz.domain.customers.model import CustomerId
from kapataz.infrastructure.persistence.tables import QuoteLineRow, QuoteRow, QuoteVersionRow
from kapataz.infrastructure.persistence.tenant_scope import TenantScope

if TYPE_CHECKING:
    from uuid import UUID


class SqlQuoteRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add(self, quote: Quote) -> None:
        self._scope.check(quote.tenant_id)
        self._session.add(
            QuoteRow(
                id=quote.id,
                tenant_id=quote.tenant_id,
                customer_id=quote.customer_id,
                series=quote.number.series.code,
                year=quote.number.year,
                number=quote.number.sequence,
                status=quote.status.value,
                created_at=quote.created_at,
            )
        )
        await self._session.flush()
        for version in quote.versions:
            await self._insert_version(quote, version)

    async def get(self, quote_id: QuoteId) -> Quote | None:
        tenant_id = self._scope.tenant_id
        row = await self._session.scalar(
            select(QuoteRow).where(QuoteRow.tenant_id == tenant_id, QuoteRow.id == quote_id)
        )
        if row is None:
            return None
        version_rows = (
            await self._session.scalars(
                select(QuoteVersionRow)
                .where(QuoteVersionRow.tenant_id == tenant_id, QuoteVersionRow.quote_id == quote_id)
                .order_by(QuoteVersionRow.version)
            )
        ).all()
        line_rows = await self._session.scalars(
            select(QuoteLineRow)
            .where(
                QuoteLineRow.tenant_id == tenant_id,
                QuoteLineRow.quote_version_id.in_([v.id for v in version_rows]),
            )
            .order_by(QuoteLineRow.position)
        )
        lines_by_version: dict[UUID, list[QuoteLine]] = defaultdict(list)
        for line_row in line_rows:
            lines_by_version[line_row.quote_version_id].append(_to_line(line_row))
        return Quote(
            id=QuoteId(row.id),
            tenant_id=TenantId(row.tenant_id),
            customer_id=CustomerId(row.customer_id),
            number=DocumentNumber(Series(row.series), row.year, row.number),
            status=QuoteStatus(row.status),
            versions=tuple(
                _to_version(version_row, lines_by_version[version_row.id])
                for version_row in version_rows
            ),
            created_at=row.created_at,
        )

    async def save(self, quote: Quote) -> None:
        """Estado, versiones nuevas y, en un borrador, su versión actual reescrita."""
        self._scope.check(quote.tenant_id)
        tenant_id = self._scope.tenant_id
        await self._session.execute(
            update(QuoteRow)
            .where(QuoteRow.tenant_id == tenant_id, QuoteRow.id == quote.id)
            .values(status=quote.status.value)
        )
        stored = {
            row.id: row.version
            for row in (
                await self._session.execute(
                    select(QuoteVersionRow.id, QuoteVersionRow.version).where(
                        QuoteVersionRow.tenant_id == tenant_id,
                        QuoteVersionRow.quote_id == quote.id,
                    )
                )
            ).all()
        }
        current_ids = {version.id for version in quote.versions}
        replaced = [version_id for version_id in stored if version_id not in current_ids]
        if replaced:
            # La versión de un borrador sustituida por otra con id nuevo (sus
            # líneas se van en cascada).
            await self._session.execute(
                delete(QuoteVersionRow).where(
                    QuoteVersionRow.tenant_id == tenant_id, QuoteVersionRow.id.in_(replaced)
                )
            )
        for version in quote.versions:
            if version.id not in stored:
                await self._insert_version(quote, version)
            elif quote.status is QuoteStatus.DRAFT and version is quote.current_version:
                await self._rewrite_version(quote, version)

    async def _insert_version(self, quote: Quote, version: QuoteVersion) -> None:
        self._session.add(
            QuoteVersionRow(
                id=version.id,
                tenant_id=quote.tenant_id,
                quote_id=quote.id,
                version=version.version,
                recipient_type=version.recipient_type.value,
                dwelling_over_two_years=version.dwelling_over_two_years,
                valid_until=version.valid_until,
                created_at=version.created_at,
            )
        )
        await self._session.flush()
        await self._insert_lines(quote.tenant_id, version)

    async def _rewrite_version(self, quote: Quote, version: QuoteVersion) -> None:
        tenant_id = self._scope.tenant_id
        await self._session.execute(
            update(QuoteVersionRow)
            .where(QuoteVersionRow.tenant_id == tenant_id, QuoteVersionRow.id == version.id)
            .values(
                recipient_type=version.recipient_type.value,
                dwelling_over_two_years=version.dwelling_over_two_years,
                valid_until=version.valid_until,
            )
        )
        await self._session.execute(
            delete(QuoteLineRow).where(
                QuoteLineRow.tenant_id == tenant_id, QuoteLineRow.quote_version_id == version.id
            )
        )
        await self._insert_lines(quote.tenant_id, version)

    async def _insert_lines(self, tenant_id: TenantId, version: QuoteVersion) -> None:
        for position, line in enumerate(version.lines, start=1):
            self._session.add(
                QuoteLineRow(
                    id=line.id,
                    tenant_id=tenant_id,
                    quote_version_id=version.id,
                    position=position,
                    description=line.description,
                    quantity=line.quantity.value,
                    unit_price=line.unit_price,
                    price_source=line.price_source.kind.value,
                    price_source_samples=line.price_source.sample_count,
                    price_source_reference_id=line.price_source.reference_id,
                    discount_pct=None if line.discount is None else line.discount.value,
                    is_material=line.is_material,
                    outside_works=line.outside_works,
                )
            )
        await self._session.flush()


def _to_version(row: QuoteVersionRow, lines: list[QuoteLine]) -> QuoteVersion:
    return QuoteVersion(
        id=QuoteVersionId(row.id),
        version=row.version,
        lines=tuple(lines),
        recipient_type=RecipientType(row.recipient_type),
        dwelling_over_two_years=row.dwelling_over_two_years,
        valid_until=row.valid_until,
        created_at=row.created_at,
    )


def _to_line(row: QuoteLineRow) -> QuoteLine:
    return QuoteLine(
        id=QuoteLineId(row.id),
        description=row.description,
        quantity=Quantity(row.quantity),
        unit_price=row.unit_price,
        price_source=PriceSource(
            kind=PriceSourceKind(row.price_source),
            sample_count=row.price_source_samples,
            reference_id=row.price_source_reference_id,
        ),
        discount=None if row.discount_pct is None else Percentage(row.discount_pct),
        is_material=row.is_material,
        outside_works=row.outside_works,
    )
