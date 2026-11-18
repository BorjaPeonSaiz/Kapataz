"""Repositorio de facturas y rectificativas, con sus líneas (RF-FA-01 a RF-FA-05, RN-F-02).

Las columnas de importe son una copia de lo que calcula el dominio
(``Invoice.totals``) para poder consultarlas; al leer, la factura vuelve a
calcularlos de sus líneas. Una factura emitida solo se escribe una vez, al
pasar de borrador a emitida; después, los triggers de la base de datos
impiden cualquier cambio (RN-F-02).
"""

from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.codes import (
    CorrectionType,
    InvoiceStatus,
    InvoiceType,
    LineOrigin,
    PhaseType,
    RecipientType,
)
from kapataz.domain.billing.errors import InvoiceAlreadyIssuedError, InvoiceNotFoundError
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.invoice import CorrectiveInvoice, Guarantee, Invoice, RectifiedInvoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.party import Party
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import OperationClass, RegimeKey, TaxRate, VatTreatment
from kapataz.domain.customers.model import CustomerId
from kapataz.domain.customers.tax_id import TaxId
from kapataz.infrastructure.persistence.tables import (
    InvoiceCorrectionRow,
    InvoiceLineRow,
    InvoiceRow,
)
from kapataz.infrastructure.persistence.tenant_scope import TenantScope

_DRAFT = InvoiceStatus.DRAFT.value


class SqlInvoiceRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add_draft(self, invoice: Invoice) -> None:
        self._scope.check(invoice.tenant_id)
        _require_draft(invoice)
        self._session.add(InvoiceRow(**_invoice_values(invoice)))
        await self._session.flush()
        await self._insert_lines(invoice)
        if isinstance(invoice, CorrectiveInvoice):
            for position, item in enumerate(invoice.rectified, start=1):
                self._session.add(
                    InvoiceCorrectionRow(
                        tenant_id=invoice.tenant_id,
                        corrective_invoice_id=invoice.id,
                        rectified_invoice_id=item.invoice_id,
                        position=position,
                        rectified_base=item.rectified_base,
                        rectified_tax=item.rectified_tax,
                    )
                )
            await self._session.flush()

    async def get(self, invoice_id: InvoiceId) -> Invoice | None:
        return await self._load(invoice_id, for_update=False)

    async def get_for_update(self, invoice_id: InvoiceId) -> Invoice | None:
        return await self._load(invoice_id, for_update=True)

    async def save_draft(self, invoice: Invoice) -> None:
        self._scope.check(invoice.tenant_id)
        _require_draft(invoice)
        # La cabecera primero: bloquea la fila antes de tocar las líneas, igual
        # que la emisión, y así dos cambios del mismo borrador no se cruzan.
        await self._update_draft_row(invoice)
        await self._session.execute(
            delete(InvoiceLineRow).where(
                InvoiceLineRow.tenant_id == self._scope.tenant_id,
                InvoiceLineRow.invoice_id == invoice.id,
            )
        )
        await self._insert_lines(invoice)

    async def delete_draft(self, invoice_id: InvoiceId) -> None:
        result = await self._session.execute(
            delete(InvoiceRow).where(
                InvoiceRow.tenant_id == self._scope.tenant_id,
                InvoiceRow.id == invoice_id,
                InvoiceRow.status == _DRAFT,
            )
        )
        if _rowcount(result) != 1:
            await self._raise_not_draft(invoice_id)

    async def mark_issued(self, invoice: Invoice) -> None:
        self._scope.check(invoice.tenant_id)
        if not invoice.is_issued:
            msg = "mark_issued recibe la factura ya emitida por el dominio."
            raise ValueError(msg)
        await self._update_draft_row(invoice)

    # ------------------------------------------------------------ internas

    async def _update_draft_row(self, invoice: Invoice) -> None:
        values = _invoice_values(invoice)
        for key in ("id", "tenant_id", "created_at"):
            values.pop(key)
        result = await self._session.execute(
            update(InvoiceRow)
            .where(
                InvoiceRow.tenant_id == self._scope.tenant_id,
                InvoiceRow.id == invoice.id,
                InvoiceRow.status == _DRAFT,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if _rowcount(result) != 1:
            await self._raise_not_draft(invoice.id)

    async def _raise_not_draft(self, invoice_id: InvoiceId) -> None:
        exists = await self._session.scalar(
            select(InvoiceRow.id).where(
                InvoiceRow.tenant_id == self._scope.tenant_id, InvoiceRow.id == invoice_id
            )
        )
        if exists is None:
            raise InvoiceNotFoundError("La factura no existe.")
        msg = "Una factura emitida no se modifica; se corrige con una rectificativa."
        raise InvoiceAlreadyIssuedError(msg)

    async def _insert_lines(self, invoice: Invoice) -> None:
        for position, line in enumerate(invoice.lines, start=1):
            self._session.add(
                InvoiceLineRow(
                    id=uuid4(),
                    tenant_id=invoice.tenant_id,
                    invoice_id=invoice.id,
                    position=position,
                    description=line.description,
                    quantity=line.quantity.value,
                    unit_price=line.unit_price,
                    discount_pct=None if line.discount is None else line.discount.value,
                    is_material=line.is_material,
                    outside_works=line.outside_works,
                    origin=None if line.origin is None else line.origin.value,
                    quote_line_id=line.quote_line_id,
                    prior_invoice_id=line.prior_invoice_id,
                )
            )
        await self._session.flush()

    async def _load(self, invoice_id: InvoiceId, *, for_update: bool) -> Invoice | None:
        tenant_id = self._scope.tenant_id
        statement = select(InvoiceRow).where(
            InvoiceRow.tenant_id == tenant_id, InvoiceRow.id == invoice_id
        )
        if for_update:
            statement = statement.with_for_update()
        row = (
            await self._session.scalars(statement.execution_options(populate_existing=True))
        ).one_or_none()
        if row is None:
            return None
        line_rows = await self._session.scalars(
            select(InvoiceLineRow)
            .where(InvoiceLineRow.tenant_id == tenant_id, InvoiceLineRow.invoice_id == invoice_id)
            .order_by(InvoiceLineRow.position)
        )
        lines = tuple(_to_line(line_row) for line_row in line_rows)
        if not InvoiceType(row.invoice_type).is_corrective:
            return Invoice(**_common_fields(row, lines), invoice_type=InvoiceType(row.invoice_type))
        return CorrectiveInvoice(
            **_common_fields(row, lines),
            invoice_type=InvoiceType(row.invoice_type),
            correction_type=CorrectionType(_required(row.correction_type)),
            rectified=await self._rectified(invoice_id),
            reason=_required(row.correction_reason),
        )

    async def _rectified(self, invoice_id: InvoiceId) -> tuple[RectifiedInvoice, ...]:
        tenant_id = self._scope.tenant_id
        rows = await self._session.execute(
            select(InvoiceCorrectionRow, InvoiceRow)
            .join(
                InvoiceRow,
                (InvoiceRow.tenant_id == InvoiceCorrectionRow.tenant_id)
                & (InvoiceRow.id == InvoiceCorrectionRow.rectified_invoice_id),
            )
            .where(
                InvoiceCorrectionRow.tenant_id == tenant_id,
                InvoiceCorrectionRow.corrective_invoice_id == invoice_id,
            )
            .order_by(InvoiceCorrectionRow.position)
        )
        return tuple(
            RectifiedInvoice(
                invoice_id=InvoiceId(correction.rectified_invoice_id),
                number=_number(rectified),
                issue_date=_required(rectified.issue_date),
                rectified_base=correction.rectified_base,
                rectified_tax=correction.rectified_tax,
            )
            for correction, rectified in rows
        )


def _require_draft(invoice: Invoice) -> None:
    if invoice.is_issued:
        msg = "Una factura emitida no se modifica; se corrige con una rectificativa."
        raise InvoiceAlreadyIssuedError(msg)


def _rowcount(result: object) -> int:
    count = getattr(result, "rowcount", None)
    if not isinstance(count, int):  # pragma: no cover - UPDATE y DELETE siempre lo dan
        msg = "La base de datos no devolvió el número de filas."
        raise TypeError(msg)
    return count


def _invoice_values(invoice: Invoice) -> dict[str, Any]:
    totals = invoice.totals
    corrective = invoice if isinstance(invoice, CorrectiveInvoice) else None
    number = invoice.number
    rate = invoice.treatment.rate
    issuer, recipient = invoice.issuer, invoice.recipient
    return {
        "id": invoice.id,
        "tenant_id": invoice.tenant_id,
        "customer_id": invoice.customer_id,
        "quote_version_id": invoice.quote_version_id,
        "status": invoice.status.value,
        "invoice_type": invoice.invoice_type.value,
        "correction_type": None if corrective is None else corrective.correction_type.value,
        "correction_reason": None if corrective is None else corrective.reason,
        "phase_type": None if invoice.phase_type is None else invoice.phase_type.value,
        "series": invoice.series.code,
        "issue_year": None if number is None else number.year,
        "number": None if number is None else number.sequence,
        "issue_date": invoice.issue_date,
        "issued_at": invoice.issued_at,
        "operation_date": invoice.operation_date,
        "due_date": invoice.due_date,
        "description": invoice.description,
        "regime_key": invoice.regime_key.value,
        "operation_class": invoice.treatment.operation_class.value,
        "tax_rate": None if rate is None else int(rate.percent),
        # La v1 no emite operaciones exentas (VatTreatment solo admite S1 y S2).
        "exemption_cause": None,
        "recipient_type": None if invoice.recipient_type is None else invoice.recipient_type.value,
        "dwelling_over_two_years": invoice.dwelling_over_two_years,
        "gross_amount": invoice.gross_amount,
        "withholding_pct": _percentage(invoice.withholding_rate),
        "guarantee_pct": None if invoice.guarantee is None else invoice.guarantee.rate.value,
        "guarantee_due_date": None if invoice.guarantee is None else invoice.guarantee.due_date,
        "base_total": totals.base,
        "tax_total": totals.tax,
        "total_amount": totals.total_amount,
        "withholding_amount": totals.withholding,
        "guarantee_amount": totals.guarantee,
        "amount_due": totals.amount_due,
        "issuer_name": None if issuer is None else issuer.name,
        "issuer_tax_id": None if issuer is None else str(issuer.tax_id),
        "issuer_address": None if issuer is None else issuer.address,
        "recipient_name": None if recipient is None else recipient.name,
        "recipient_tax_id": None if recipient is None else str(recipient.tax_id),
        "recipient_address": None if recipient is None else recipient.address,
        "created_at": invoice.created_at,
    }


def _common_fields(row: InvoiceRow, lines: tuple[LineItem, ...]) -> dict[str, Any]:
    """Campos comunes a ``Invoice`` y ``CorrectiveInvoice``; el dominio los vuelve a validar."""
    issued = row.status == InvoiceStatus.ISSUED.value
    return {
        "id": InvoiceId(row.id),
        "tenant_id": TenantId(row.tenant_id),
        "customer_id": CustomerId(row.customer_id),
        "series": Series(row.series),
        "treatment": VatTreatment(
            OperationClass(row.operation_class),
            None if row.tax_rate is None else TaxRate(Decimal(row.tax_rate)),
        ),
        "lines": lines,
        "created_at": row.created_at,
        "description": row.description,
        "regime_key": RegimeKey(row.regime_key),
        "phase_type": None if row.phase_type is None else PhaseType(row.phase_type),
        "quote_version_id": (
            None if row.quote_version_id is None else QuoteVersionId(row.quote_version_id)
        ),
        "recipient_type": None if row.recipient_type is None else RecipientType(row.recipient_type),
        "dwelling_over_two_years": row.dwelling_over_two_years,
        "gross_amount": row.gross_amount,
        "withholding_rate": (
            None if row.withholding_pct is None else Percentage(row.withholding_pct)
        ),
        "guarantee": (
            None
            if row.guarantee_pct is None or row.guarantee_due_date is None
            else Guarantee(rate=Percentage(row.guarantee_pct), due_date=row.guarantee_due_date)
        ),
        "operation_date": row.operation_date,
        "due_date": row.due_date,
        "status": InvoiceStatus(row.status),
        "number": _number(row) if issued else None,
        "issue_date": row.issue_date,
        "issued_at": row.issued_at,
        "issuer": _party(row.issuer_name, row.issuer_tax_id, row.issuer_address),
        "recipient": _party(row.recipient_name, row.recipient_tax_id, row.recipient_address),
    }


def _to_line(row: InvoiceLineRow) -> LineItem:
    return LineItem(
        description=row.description,
        quantity=Quantity(row.quantity),
        unit_price=row.unit_price,
        discount=None if row.discount_pct is None else Percentage(row.discount_pct),
        is_material=row.is_material,
        outside_works=row.outside_works,
        origin=None if row.origin is None else LineOrigin(row.origin),
        quote_line_id=None if row.quote_line_id is None else QuoteLineId(row.quote_line_id),
        prior_invoice_id=None if row.prior_invoice_id is None else InvoiceId(row.prior_invoice_id),
    )


def _number(row: InvoiceRow) -> DocumentNumber:
    return DocumentNumber(Series(row.series), _required(row.issue_year), _required(row.number))


def _party(name: str | None, tax_id: str | None, address: str | None) -> Party | None:
    if name is None or tax_id is None:
        return None
    return Party(name, TaxId(tax_id), address)


def _percentage(value: Percentage | None) -> Decimal | None:
    return None if value is None else value.value


def _required[T](value: T | None) -> T:
    if value is None:
        msg = "Falta un dato que la base de datos garantiza para esta fila."
        raise ValueError(msg)
    return value
