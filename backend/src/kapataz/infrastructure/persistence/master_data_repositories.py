"""Repositorios de datos maestros: profesional, clientes, catálogo y cobros.

Todos filtran por la cuenta fijada (``TenantScope``); RLS vuelve a hacerlo en
la base de datos (ADR-024).
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.ids import InvoiceId, PaymentId
from kapataz.domain.billing.payment import Payment, PaymentMethod
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from kapataz.domain.customers.errors import DuplicateCustomerTaxIdError
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.customers.tax_id import TaxId
from kapataz.domain.settings.professional import Professional
from kapataz.infrastructure.persistence.tables import (
    CatalogItemRow,
    CustomerRow,
    PaymentRow,
    ProfessionalRow,
)
from kapataz.infrastructure.persistence.tenant_scope import TenantScope

_CUSTOMER_TAX_ID_CONSTRAINT = "uq_customers_tenant_id_tax_id"
# La v1 solo admite NIF español (§1.4).
_SPANISH_NIF_TYPE = "nif"
_SPAIN = "ES"


class SqlProfessionalRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def get(self) -> Professional | None:
        row = await self._session.scalar(
            select(ProfessionalRow).where(ProfessionalRow.tenant_id == self._scope.tenant_id)
        )
        if row is None:
            return None
        return Professional(
            tenant_id=TenantId(row.tenant_id),
            name=row.name,
            tax_id=None if row.tax_id is None else TaxId(row.tax_id),
            address=row.address,
            updated_at=row.updated_at,
        )

    async def save(self, professional: Professional) -> None:
        self._scope.check(professional.tenant_id)
        values = {
            "name": professional.name,
            "tax_id": None if professional.tax_id is None else str(professional.tax_id),
            "address": professional.address,
            "updated_at": professional.updated_at,
        }
        statement = pg_insert(ProfessionalRow).values(tenant_id=professional.tenant_id, **values)
        await self._session.execute(
            statement.on_conflict_do_update(index_elements=["tenant_id"], set_=values)
        )


class SqlCustomerRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add(self, customer: Customer) -> None:
        self._scope.check(customer.tenant_id)
        has_tax_id = customer.tax_id is not None
        self._session.add(
            CustomerRow(
                id=customer.id,
                tenant_id=customer.tenant_id,
                name=customer.name,
                tax_id=None if customer.tax_id is None else str(customer.tax_id),
                tax_id_type=_SPANISH_NIF_TYPE if has_tax_id else None,
                tax_id_country=_SPAIN if has_tax_id else None,
                address=customer.address,
                created_at=customer.created_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _CUSTOMER_TAX_ID_CONSTRAINT in str(error.orig):
                msg = "Ya hay un cliente con ese NIF."
                raise DuplicateCustomerTaxIdError(msg) from None
            raise

    async def get(self, customer_id: CustomerId) -> Customer | None:
        row = await self._session.scalar(
            select(CustomerRow).where(
                CustomerRow.tenant_id == self._scope.tenant_id, CustomerRow.id == customer_id
            )
        )
        if row is None:
            return None
        return Customer(
            id=CustomerId(row.id),
            tenant_id=TenantId(row.tenant_id),
            name=row.name,
            tax_id=None if row.tax_id is None else TaxId(row.tax_id),
            address=row.address,
            created_at=row.created_at,
        )


class SqlCatalogRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add(self, item: CatalogItem) -> None:
        self._scope.check(item.tenant_id)
        self._session.add(
            CatalogItemRow(
                id=item.id,
                tenant_id=item.tenant_id,
                concept=item.concept,
                unit=item.unit,
                reference_price=item.reference_price,
                origin=item.origin.value,
                is_material=item.is_material,
                created_at=item.created_at,
            )
        )
        await self._session.flush()

    async def get(self, item_id: CatalogItemId) -> CatalogItem | None:
        row = await self._session.scalar(
            select(CatalogItemRow).where(
                CatalogItemRow.tenant_id == self._scope.tenant_id, CatalogItemRow.id == item_id
            )
        )
        if row is None:
            return None
        return CatalogItem(
            id=CatalogItemId(row.id),
            tenant_id=TenantId(row.tenant_id),
            concept=row.concept,
            unit=row.unit,
            reference_price=row.reference_price,
            origin=CatalogItemOrigin(row.origin),
            is_material=row.is_material,
            created_at=row.created_at,
        )


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add(self, payment: Payment) -> None:
        self._scope.check(payment.tenant_id)
        self._session.add(
            PaymentRow(
                id=payment.id,
                tenant_id=payment.tenant_id,
                invoice_id=payment.invoice_id,
                amount=payment.amount,
                paid_at=payment.paid_at,
                method=payment.method.value,
                created_at=payment.created_at,
            )
        )
        await self._session.flush()

    async def list_for_invoice(self, invoice_id: InvoiceId) -> tuple[Payment, ...]:
        rows = await self._session.scalars(
            select(PaymentRow)
            .where(
                PaymentRow.tenant_id == self._scope.tenant_id,
                PaymentRow.invoice_id == invoice_id,
            )
            .order_by(PaymentRow.paid_at, PaymentRow.created_at, PaymentRow.id)
        )
        return tuple(
            Payment(
                id=PaymentId(row.id),
                tenant_id=TenantId(row.tenant_id),
                invoice_id=InvoiceId(row.invoice_id),
                amount=row.amount,
                paid_at=row.paid_at,
                method=PaymentMethod(row.method),
                created_at=row.created_at,
            )
            for row in rows
        )
