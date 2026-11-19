"""Constructores de objetos de facturación para las pruebas del dominio.

Solo rellenan lo que cada prueba no necesita mirar; lo que se comprueba se
pasa siempre de forma explícita.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.billing_record import SystemInfo
from kapataz.domain.billing.codes import (
    CorrectionType,
    InvoiceType,
    LineOrigin,
    PhaseType,
    RecipientType,
)
from kapataz.domain.billing.ids import InvoiceId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.invoice import CorrectiveInvoice, Invoice, RectifiedInvoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.party import Party
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.quote import QuoteVersion
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.domain.customers.model import CustomerId
from kapataz.domain.customers.tax_id import TaxId

NOW = datetime(2026, 11, 18, 9, 30, tzinfo=UTC)
TODAY = date(2026, 11, 18)
TENANT = TenantId(uuid4())
CUSTOMER = CustomerId(uuid4())
# NIF sintéticos con el dígito de control correcto (ADR-020).
ISSUER = Party("Reformas Ejemplo", TaxId("12345678Z"), "Calle Mayor 1, 28001 Madrid")
RECIPIENT = Party("Cliente Ejemplo", TaxId("B12345674"), "Avenida del Puerto 2, 46021 Valencia")
GENERAL = VatTreatment.taxed(TaxRate.general())
REDUCED = VatTreatment.taxed(TaxRate.reduced())
SYSTEM = SystemInfo(
    producer_name="KodigoLab",
    producer_tax_id=TaxId("A58818501"),
    system_name="Kapataz",
    system_id="KZ",
    version="0123abc",
    installation_number="local-1",
    only_verifactu=True,
    multi_taxpayer=True,
    has_multiple_taxpayers=True,
)


def money(amount: str) -> Money:
    return Money(Decimal(amount))


def line(
    price: str,
    quantity: str = "1",
    *,
    description: str = "Trabajo",
    is_material: bool = False,
    outside_works: bool = False,
    origin: LineOrigin | None = None,
    quote_line_id: QuoteLineId | None = None,
) -> LineItem:
    if origin is LineOrigin.QUOTE and quote_line_id is None:
        quote_line_id = QuoteLineId(uuid4())
    return LineItem(
        description=description,
        quantity=Quantity(Decimal(quantity)),
        unit_price=money(price),
        is_material=is_material,
        outside_works=outside_works,
        origin=origin,
        quote_line_id=quote_line_id,
    )


def draft(
    *lines: LineItem,
    treatment: VatTreatment = GENERAL,
    description: str | None = "Reforma de baño",
    recipient_type: RecipientType | None = RecipientType.BUSINESS,
    dwelling_over_two_years: bool | None = None,
    phase_type: PhaseType = PhaseType.FULL,
    quote_version_id: QuoteVersionId | None = None,
    series: Series | None = None,
) -> Invoice:
    if quote_version_id is not None:
        recipient_type = None
    return Invoice(
        id=InvoiceId(uuid4()),
        tenant_id=TENANT,
        customer_id=CUSTOMER,
        series=series or Series.invoices(),
        treatment=treatment,
        lines=lines,
        created_at=NOW,
        description=description,
        phase_type=phase_type,
        quote_version_id=quote_version_id,
        recipient_type=recipient_type,
        dwelling_over_two_years=dwelling_over_two_years,
    )


def quote_version(
    version_id: QuoteVersionId | None = None,
    *,
    recipient_type: RecipientType = RecipientType.PRIVATE,
    dwelling_over_two_years: bool | None = True,
) -> QuoteVersion:
    """Versión sin líneas: para emitir solo cuentan su id, el destinatario y la vivienda."""
    return QuoteVersion(
        id=version_id or QuoteVersionId(uuid4()),
        version=1,
        lines=(),
        recipient_type=recipient_type,
        dwelling_over_two_years=dwelling_over_two_years,
        valid_until=None,
        created_at=NOW,
    )


def issue(
    invoice: Invoice,
    sequence: int = 1,
    issue_date: date = TODAY,
    *,
    version: QuoteVersion | None = None,
) -> Invoice:
    """Emite con las partes de prueba.

    Si la factura sale de un presupuesto y no se da ``version``, se emite con
    una de un particular con vivienda de más de dos años, que admite el 10 % y
    el 21 %. Las pruebas que miran el destinatario pasan su versión.
    """
    if version is None and invoice.quote_version_id is not None:
        version = quote_version(invoice.quote_version_id)
    return invoice.issue(
        number=DocumentNumber(invoice.series, issue_date.year, sequence),
        issue_date=issue_date,
        issued_at=NOW,
        issuer=ISSUER,
        recipient=RECIPIENT,
        last_issue_date=None,
        quote_version=version,
    )


def corrective(
    *lines: LineItem,
    rectified: tuple[RectifiedInvoice, ...],
    correction_type: CorrectionType = CorrectionType.DIFFERENCE,
    invoice_type: InvoiceType = InvoiceType.R1,
    reason: str = "Trabajos no realizados",
) -> CorrectiveInvoice:
    return CorrectiveInvoice(
        id=InvoiceId(uuid4()),
        tenant_id=TENANT,
        customer_id=CUSTOMER,
        series=Series.correctives(),
        treatment=GENERAL,
        lines=lines,
        created_at=NOW,
        description="Rectificación",
        recipient_type=RecipientType.BUSINESS,
        invoice_type=invoice_type,
        correction_type=correction_type,
        rectified=rectified,
        reason=reason,
    )
