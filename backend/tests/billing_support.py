"""Datos de partida de facturación para las pruebas de emisión.

Funcionan con cualquier ``UnitOfWorkFactory``: la de memoria
(``MemoryUnitOfWorkFactory``) y la de PostgreSQL
(``SqlAlchemyUnitOfWorkFactory``). Así las pruebas unitarias del caso de uso,
las de integración y las de concurrencia parten de los mismos datos.

Todos los datos son sintéticos (ADR-020): NIF con el dígito de control
correcto, pero inventados.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.domain.accounts.model import Tenant, TenantId, TenantKind
from kapataz.domain.billing.billing_record import SystemInfo
from kapataz.domain.billing.codes import CorrectionType, InvoiceType, RecipientType
from kapataz.domain.billing.ids import InvoiceId
from kapataz.domain.billing.invoice import CorrectiveInvoice, Invoice, RectifiedInvoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import Series
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.customers.tax_id import TaxId
from kapataz.domain.settings.professional import Professional

SEED_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
ISSUER_TAX_ID = TaxId("12345678Z")
ISSUER_ADDRESS = "Calle Mayor 1, 28001 Madrid"
RECIPIENT_TAX_ID = TaxId("B12345674")
RECIPIENT_ADDRESS = "Avenida del Puerto 2, 46021 Valencia"
GENERAL = VatTreatment.taxed(TaxRate.general())
SYSTEM = SystemInfo(
    producer_name="KodigoLab",
    producer_tax_id=TaxId("A58818501"),
    system_name="Kapataz",
    system_id="KZ",
    version="0123abc",
    installation_number="pruebas-1",
    only_verifactu=True,
    multi_taxpayer=True,
    has_multiple_taxpayers=True,
)
_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def synthetic_dni(number: int) -> TaxId:
    """DNI sintético válido a partir de un número de 0 a 99.999.999."""
    return TaxId(f"{number:08d}{_DNI_LETTERS[number % 23]}")


def two_lines() -> tuple[LineItem, ...]:
    """1.000 € de mano de obra y 250 € de material: 1.250 € de base, 262,50 € de IVA."""
    return (
        LineItem(
            description="Mano de obra",
            quantity=Quantity(Decimal(10)),
            unit_price=Money(Decimal("100.00")),
        ),
        LineItem(
            description="Material",
            quantity=Quantity(Decimal("2.5")),
            unit_price=Money(Decimal("100.00")),
            is_material=True,
        ),
    )


async def create_account(
    factory: UnitOfWorkFactory,
    *,
    with_professional: bool = True,
    professional_address: str | None = ISSUER_ADDRESS,
) -> TenantId:
    """Cuenta normal con los datos del profesional (emisor)."""
    tenant_id = TenantId(uuid4())
    async with factory() as uow:
        await uow.set_tenant(tenant_id)
        await uow.accounts.add_tenant(
            Tenant(
                id=tenant_id,
                name=None,
                kind=TenantKind.STANDARD,
                parent_tenant_id=None,
                created_at=SEED_AT,
            )
        )
        if with_professional:
            await uow.professional.save(
                Professional(
                    tenant_id=tenant_id,
                    name="Reformas Ejemplo",
                    tax_id=ISSUER_TAX_ID,
                    address=professional_address,
                    updated_at=SEED_AT,
                )
            )
        await uow.commit()
    return tenant_id


async def add_customer(
    factory: UnitOfWorkFactory,
    tenant_id: TenantId,
    *,
    tax_id: TaxId | None = RECIPIENT_TAX_ID,
    address: str | None = RECIPIENT_ADDRESS,
) -> CustomerId:
    customer_id = CustomerId(uuid4())
    async with factory() as uow:
        await uow.set_tenant(tenant_id)
        await uow.customers.add(
            Customer(
                id=customer_id,
                tenant_id=tenant_id,
                name="Cliente Ejemplo",
                tax_id=tax_id,
                address=address,
                created_at=SEED_AT,
            )
        )
        await uow.commit()
    return customer_id


def draft_invoice(
    tenant_id: TenantId,
    customer_id: CustomerId,
    *,
    series: Series | None = None,
    description: str | None = "Reforma de baño",
    lines: tuple[LineItem, ...] | None = None,
) -> Invoice:
    return Invoice(
        id=InvoiceId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        series=series or Series.invoices(),
        treatment=GENERAL,
        lines=two_lines() if lines is None else lines,
        created_at=SEED_AT,
        description=description,
        recipient_type=RecipientType.BUSINESS,
    )


async def add_draft(
    factory: UnitOfWorkFactory,
    tenant_id: TenantId,
    customer_id: CustomerId,
    *,
    series: Series | None = None,
    description: str | None = "Reforma de baño",
) -> InvoiceId:
    draft = draft_invoice(tenant_id, customer_id, series=series, description=description)
    async with factory() as uow:
        await uow.set_tenant(tenant_id)
        await uow.invoices.add_draft(draft)
        await uow.commit()
    return draft.id


async def issuable_drafts(
    factory: UnitOfWorkFactory, count: int, *, series: Series | None = None
) -> tuple[TenantId, list[InvoiceId]]:
    """Cuenta nueva con su cliente y ``count`` borradores listos para emitir."""
    tenant_id = await create_account(factory)
    customer_id = await add_customer(factory, tenant_id)
    drafts = [await add_draft(factory, tenant_id, customer_id, series=series) for _ in range(count)]
    return tenant_id, drafts


def corrective_of(
    tenant_id: TenantId, customer_id: CustomerId, rectified: Invoice
) -> CorrectiveInvoice:
    """Borrador de rectificativa por diferencias (serie R, R1) de una factura emitida."""
    if rectified.number is None or rectified.issue_date is None:
        msg = "Solo se rectifica una factura emitida."
        raise ValueError(msg)
    return CorrectiveInvoice(
        id=InvoiceId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        series=Series.correctives(),
        treatment=GENERAL,
        lines=two_lines(),
        created_at=SEED_AT,
        description="Rectificación del precio",
        recipient_type=RecipientType.BUSINESS,
        invoice_type=InvoiceType.R1,
        correction_type=CorrectionType.DIFFERENCE,
        rectified=(
            RectifiedInvoice(
                invoice_id=rectified.id,
                number=rectified.number,
                issue_date=rectified.issue_date,
            ),
        ),
        reason="Precio unitario equivocado",
    )


async def add_corrective_draft(
    factory: UnitOfWorkFactory, tenant_id: TenantId, customer_id: CustomerId, rectified: Invoice
) -> InvoiceId:
    draft = corrective_of(tenant_id, customer_id, rectified)
    async with factory() as uow:
        await uow.set_tenant(tenant_id)
        await uow.invoices.add_draft(draft)
        await uow.commit()
    return draft.id
