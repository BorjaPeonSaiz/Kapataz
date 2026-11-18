"""Ida y vuelta de cada repositorio de facturación contra PostgreSQL real."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from kapataz.domain.billing.codes import CorrectionType, InvoiceType, LineOrigin, RecipientType
from kapataz.domain.billing.errors import InvoiceAlreadyIssuedError, InvoiceNotFoundError
from kapataz.domain.billing.ids import InvoiceId, PaymentId, QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.invoice import (
    CorrectiveInvoice,
    Guarantee,
    Invoice,
    RectifiedInvoice,
)
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.payment import Payment, PaymentMethod
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.quote import (
    PriceSource,
    PriceSourceKind,
    Quote,
    QuoteLine,
    QuoteStatus,
    QuoteVersion,
)
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from kapataz.domain.customers.errors import DuplicateCustomerTaxIdError
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.settings.professional import Professional
from tests.billing_support import (
    GENERAL,
    RECIPIENT_TAX_ID,
    SEED_AT,
    add_customer,
    create_account,
    draft_invoice,
    synthetic_dni,
)
from tests.integration.persistence.conftest import issue_new

REDUCED = VatTreatment.taxed(TaxRate.reduced())


def _in_tenant(factory, tenant_id, action):
    """Ejecuta ``action(uow)`` en una transacción de la cuenta y confirma."""

    async def run():
        async with factory() as uow:
            await uow.set_tenant(tenant_id)
            result = await action(uow)
            await uow.commit()
            return result

    return asyncio.run(run())


@pytest.mark.req("RF-CF-01")
def test_profesional_ida_y_vuelta_y_sustitucion(app_factory):
    tenant_id = asyncio.run(create_account(app_factory, with_professional=False))
    first = Professional(
        tenant_id=tenant_id, name="Reformas Uno", tax_id=None, address=None, updated_at=SEED_AT
    )
    changed = Professional(
        tenant_id=tenant_id,
        name="Reformas Dos",
        tax_id=synthetic_dni(11111111),
        address="Calle Nueva 3, 28002 Madrid",
        updated_at=datetime(2026, 11, 19, 8, 0, tzinfo=UTC),
    )

    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.professional.get()) is None
    _in_tenant(app_factory, tenant_id, lambda uow: uow.professional.save(first))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.professional.get()) == first
    _in_tenant(app_factory, tenant_id, lambda uow: uow.professional.save(changed))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.professional.get()) == changed


@pytest.mark.req("RN-F-06")
def test_cliente_ida_y_vuelta_y_nif_unico_por_cuenta(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    other_tenant = asyncio.run(create_account(app_factory))
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=tenant_id,
        name="Comunidad Calle Sol 4",
        tax_id=RECIPIENT_TAX_ID,
        address="Calle Sol 4, 41001 Sevilla",
        created_at=SEED_AT,
    )
    without_tax_id = Customer(
        id=CustomerId(uuid4()),
        tenant_id=tenant_id,
        name="Cliente sin NIF",
        tax_id=None,
        address=None,
        created_at=SEED_AT,
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.customers.add(customer))
    _in_tenant(app_factory, tenant_id, lambda uow: uow.customers.add(without_tax_id))

    assert (
        _in_tenant(app_factory, tenant_id, lambda uow: uow.customers.get(customer.id)) == customer
    )
    loaded = _in_tenant(app_factory, tenant_id, lambda uow: uow.customers.get(without_tax_id.id))
    assert loaded == without_tax_id
    with pytest.raises(DuplicateCustomerTaxIdError):
        asyncio.run(add_customer(app_factory, tenant_id, tax_id=RECIPIENT_TAX_ID))
    # El mismo NIF en otra cuenta no choca: es único por cuenta.
    asyncio.run(add_customer(app_factory, other_tenant, tax_id=RECIPIENT_TAX_ID))


@pytest.mark.req("RF-CF-02")
@pytest.mark.req("RN-01")
def test_concepto_del_catalogo_ida_y_vuelta(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    priced = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept="Punto de luz",
        unit="ud",
        reference_price=Money.of("45.90"),
        origin=CatalogItemOrigin.MANUAL,
        is_material=False,
        created_at=SEED_AT,
    )
    unpriced = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept="Cable 2,5 mm",
        unit="m",
        reference_price=None,
        origin=CatalogItemOrigin.HISTORY,
        is_material=True,
        created_at=SEED_AT,
    )
    for item in (priced, unpriced):
        _in_tenant(app_factory, tenant_id, lambda uow, item=item: uow.catalog.add(item))
        assert (
            _in_tenant(app_factory, tenant_id, lambda uow, item=item: uow.catalog.get(item.id))
            == item
        )


def _quote_line(price: str | None, *, position_text: str = "Alicatado") -> QuoteLine:
    return QuoteLine(
        id=QuoteLineId(uuid4()),
        description=position_text,
        quantity=Quantity(Decimal("12.375")),
        unit_price=None if price is None else Money.of(price),
        price_source=PriceSource.none() if price is None else PriceSource.manual(),
        discount=None if price is None else Percentage(Decimal("5.5")),
        is_material=price is not None,
    )


def _version(number: int, *lines: QuoteLine) -> QuoteVersion:
    return QuoteVersion(
        id=QuoteVersionId(uuid4()),
        version=number,
        lines=lines,
        recipient_type=RecipientType.PRIVATE,
        dwelling_over_two_years=True,
        valid_until=date(2026, 12, 31),
        created_at=SEED_AT,
    )


@pytest.mark.req("RF-PR-04")
def test_presupuesto_con_versiones_ida_y_vuelta(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    history = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Mano de obra",
        quantity=Quantity(Decimal(8)),
        unit_price=Money.of("35.00"),
        price_source=PriceSource(kind=PriceSourceKind.HISTORY_MEDIAN, sample_count=5),
    )
    quote = Quote(
        id=QuoteId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        number=DocumentNumber(Series.quotes(), 2026, 7),
        status=QuoteStatus.DRAFT,
        versions=(_version(1, _quote_line("24.50"), _quote_line(None), history),),
        created_at=SEED_AT,
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.add(quote))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.get(quote.id)) == quote

    # Un borrador sustituye su versión actual, aunque la nueva traiga otro id.
    revised = quote.revise(_version(1, _quote_line("30.00")))
    _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.save(revised))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.get(quote.id)) == revised

    # Enviado y modificado: versión nueva y la anterior se conserva.
    sent = revised.send()
    _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.save(sent))
    second = sent.revise(_version(2, _quote_line("31.00"), history))
    _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.save(second))
    loaded = _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.get(quote.id))
    assert loaded == second
    assert [v.version for v in loaded.versions] == [1, 2]


@pytest.mark.req("RF-FA-01")
@pytest.mark.req("RN-01")
def test_borrador_ida_y_vuelta_edicion_y_borrado(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    draft = Invoice(
        id=InvoiceId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        series=Series.invoices(),
        treatment=REDUCED,
        lines=(
            LineItem(
                description="Reforma de cocina",
                quantity=Quantity(Decimal("1.5")),
                unit_price=Money.of("1999.99"),
                discount=Percentage(Decimal("7.25")),
            ),
        ),
        created_at=SEED_AT,
        description="Cocina",
        recipient_type=RecipientType.PRIVATE,
        dwelling_over_two_years=True,
        withholding_rate=Percentage(Decimal(15)),
        guarantee=Guarantee(rate=Percentage(Decimal(5)), due_date=date(2027, 11, 18)),
        operation_date=date(2026, 11, 10),
        due_date=date(2026, 12, 18),
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.add_draft(draft))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(draft.id)) == draft

    edited = draft.with_description("Cocina y baño").add_line(
        LineItem(description="Grifo", quantity=Quantity.one(), unit_price=Money.of("80.00"))
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.save_draft(edited))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(draft.id)) == edited

    _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.delete_draft(draft.id))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(draft.id)) is None
    with pytest.raises(InvoiceNotFoundError):
        _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.delete_draft(draft.id))


@pytest.mark.req("RN-F-03")
@pytest.mark.req("RN-F-02")
def test_rectificativa_ida_y_vuelta_y_emitida_intocable(app_factory):
    tenant_id, [issued] = issue_new(app_factory)
    original = issued.invoice
    loaded_original = _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(original.id))
    assert loaded_original == original
    assert original.number is not None
    assert original.issue_date is not None

    corrective = CorrectiveInvoice(
        id=InvoiceId(uuid4()),
        tenant_id=tenant_id,
        customer_id=original.customer_id,
        series=Series.correctives(),
        treatment=original.treatment,
        lines=original.lines,
        created_at=SEED_AT,
        description="Rectificación por error en el domicilio",
        recipient_type=RecipientType.BUSINESS,
        invoice_type=InvoiceType.R1,
        correction_type=CorrectionType.SUBSTITUTION,
        rectified=(
            RectifiedInvoice(
                invoice_id=original.id,
                number=original.number,
                issue_date=original.issue_date,
                rectified_base=original.totals.base,
                rectified_tax=original.totals.tax,
            ),
        ),
        reason="Domicilio del cliente equivocado",
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.add_draft(corrective))
    loaded = _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(corrective.id))
    assert loaded == corrective
    assert isinstance(loaded, CorrectiveInvoice)

    with pytest.raises(InvoiceAlreadyIssuedError):
        _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.save_draft(original))
    with pytest.raises(InvoiceAlreadyIssuedError):
        _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.delete_draft(original.id))


@pytest.mark.req("RF-FA-03")
def test_linea_que_cita_el_presupuesto_ida_y_vuelta(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    quote_line = _quote_line("24.50")
    version = _version(1, quote_line)
    quote = Quote(
        id=QuoteId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        number=DocumentNumber(Series.quotes(), 2026, 1),
        status=QuoteStatus.DRAFT,
        versions=(version,),
        created_at=SEED_AT,
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.quotes.add(quote))
    invoice_line = quote_line.to_invoice_line()
    extra = LineItem(
        description="Trabajo adicional",
        quantity=Quantity.one(),
        unit_price=Money.of("60.00"),
        origin=LineOrigin.ADDITIONAL,
    )
    draft = Invoice(
        id=InvoiceId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        series=Series.invoices(),
        treatment=GENERAL,
        lines=(invoice_line, extra),
        created_at=SEED_AT,
        description="Alicatado",
        quote_version_id=version.id,
    )
    _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.add_draft(draft))
    assert _in_tenant(app_factory, tenant_id, lambda uow: uow.invoices.get(draft.id)) == draft


@pytest.mark.req("RF-FA-06")
@pytest.mark.req("RN-01")
def test_cobros_ida_y_vuelta(app_factory):
    tenant_id, [issued] = issue_new(app_factory)
    payments = [
        Payment(
            id=PaymentId(uuid4()),
            tenant_id=tenant_id,
            invoice_id=issued.invoice.id,
            amount=Money.of(amount),
            paid_at=paid_at,
            method=method,
            created_at=SEED_AT,
        )
        for amount, paid_at, method in (
            ("500.00", date(2026, 11, 20), PaymentMethod.BIZUM),
            ("1012.50", date(2026, 11, 25), PaymentMethod.TRANSFER),
        )
    ]
    for payment in payments:
        _in_tenant(app_factory, tenant_id, lambda uow, p=payment: uow.payments.add(p))

    loaded = _in_tenant(
        app_factory, tenant_id, lambda uow: uow.payments.list_for_invoice(issued.invoice.id)
    )
    assert loaded == tuple(payments)


# Sin req: comprueba el constructor de datos de partida que comparten las pruebas de emisión.
def test_draft_invoice_de_apoyo_es_un_borrador_valido():
    draft = draft_invoice(uuid4(), uuid4())
    assert not draft.is_issued
    assert draft.totals.total_amount == Money.of("1512.50")
