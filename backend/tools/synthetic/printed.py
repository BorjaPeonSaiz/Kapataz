"""Lo que imprime cada documento, con ``Decimal`` (ADR-020).

``printed_document`` reúne en un solo sitio lo que sale en el PDF: las partes,
las líneas (con la instrucción inyectada si es una trampa de concepto), los
importes impresos (con el error sembrado, si lo hay) y las notas. El render
de los PDF y la verdad de referencia parten de aquí, así no pueden divergir.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from synthetic import fiscal
from synthetic.amounts import Totals, compute_totals, printed_totals
from synthetic.formats import date_slash, es_percent
from synthetic.model import (
    DocumentSpec,
    InvoiceData,
    LineData,
    OtherDocumentData,
    OtherKind,
    PartyData,
    ProfessionalDataset,
    QuoteData,
    SeededErrorKind,
    Trade,
    TrapData,
    TrapTechnique,
)

_TOWN = re.compile(r"\d{5} (?P<town>.+?) \(Cantabria\)$")


@dataclass(frozen=True, slots=True, kw_only=True)
class PrintedLine:
    """Línea tal como se imprime. ``code`` es el código de artículo del programa."""

    code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal | None
    discount: Decimal | None
    amount: Decimal | None
    vat_rate: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PrintedDocument:
    """Contenido impreso de un documento, sin decidir aún su aspecto."""

    spec: DocumentSpec
    title: str
    number_label: str
    number: str
    issue_date: date
    valid_until: date | None
    due_date: date | None
    issuer: PartyData
    issuer_trade_name: str | None
    issuer_activity: str | None
    issuer_town: str
    customer_label: str
    customer: PartyData
    subject: str | None
    references: tuple[str, ...]
    lines: tuple[PrintedLine, ...]
    priced: bool
    totals: Totals | None
    correct_totals: Totals | None
    notes: tuple[str, ...]
    iban: str | None
    signatory: str | None
    paragraphs: tuple[str, ...]
    registry: str | None
    mentioned: tuple[PartyData, ...]
    omitted_customer_tax_id: str | None = None

    @property
    def trap(self) -> TrapData | None:
        return self.spec.trap

    @property
    def multi_rate(self) -> bool:
        return len({line.vat_rate for line in self.lines}) > 1


def printed_document(spec: DocumentSpec, data: ProfessionalDataset) -> PrintedDocument:
    if spec.invoice is not None:
        return _from_invoice(spec, spec.invoice, data)
    if spec.quote is not None:
        return _from_quote(spec, spec.quote, data)
    if spec.other is not None:
        return _from_other(spec, spec.other, data)
    raise AssertionError("Un documento sale de una factura, un presupuesto u otro.")


def _issuer(data: ProfessionalDataset) -> PartyData:
    p = data.professional
    return PartyData(name=p.name, tax_id=p.tax_id, address=p.address, phone=p.phone, email=p.email)


def _town(address: str) -> str:
    match = _TOWN.search(address)
    return match.group("town") if match else "Santander"


def _registry(data: ProfessionalDataset) -> str:
    digits = data.professional.tax_id[:8]
    if data.professional.trade is Trade.ELECTRICIAN:
        return (
            f"Empresa instaladora en baja tensión inscrita en Cantabria con el n.º 39-{digits[2:7]}"
        )
    return f"Inscrita en el Registro de Empresas Acreditadas (REA) con el n.º 06390{digits[3:8]}"


def _codes(data: ProfessionalDataset) -> dict[str, str]:
    prefix = "EL" if data.professional.trade is Trade.ELECTRICIAN else "AL"
    return {entry.key: f"{prefix}{index:03d}" for index, entry in enumerate(data.catalog, 1)}


def _lines(
    spec: DocumentSpec,
    lines: tuple[LineData, ...],
    data: ProfessionalDataset,
    *,
    priced: bool,
) -> tuple[PrintedLine, ...]:
    codes = _codes(data)
    printed: list[PrintedLine] = []
    for index, line in enumerate(lines):
        description = line.description
        trap = spec.trap
        if trap and trap.technique is TrapTechnique.LINE_CONCEPT and trap.line_index == index:
            description = f"{description} {trap.injected_text}"
        printed.append(
            PrintedLine(
                code=codes.get(line.catalog_key or "", "VARIOS"),
                description=description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price if priced else None,
                discount=line.discount if priced else None,
                amount=line.amount if priced else None,
                vat_rate=line.vat_rate if priced else None,
            ),
        )
    return tuple(printed)


def _customer(spec: DocumentSpec, data: ProfessionalDataset, key: str) -> PartyData:
    customer = data.customer(key)
    tax_id: str | None = customer.tax_id
    if spec.seeded_error is SeededErrorKind.MISSING_TAX_ID:
        tax_id = None
    return PartyData(name=customer.name, tax_id=tax_id, address=customer.address)


def _omitted_tax_id(spec: DocumentSpec, data: ProfessionalDataset, key: str) -> str | None:
    if spec.seeded_error is SeededErrorKind.MISSING_TAX_ID:
        return data.customer(key).tax_id
    return None


def _totals(
    spec: DocumentSpec,
    lines: tuple[LineData, ...],
    *,
    reverse_charge: bool,
    withholding: Decimal | None,
    guarantee: Decimal | None,
) -> tuple[Totals, Totals]:
    correct = compute_totals(
        lines,
        reverse_charge=reverse_charge,
        withholding_rate=withholding,
        guarantee_rate=guarantee,
    )
    return correct, printed_totals(correct, spec.seeded_error, spec.error_variant)


def _vat_note(totals: Totals) -> str | None:
    if totals.reverse_charge:
        return fiscal.REVERSE_CHARGE_TEXT
    return None


def _from_invoice(
    spec: DocumentSpec,
    invoice: InvoiceData,
    data: ProfessionalDataset,
) -> PrintedDocument:
    correct, printed = _totals(
        spec,
        invoice.lines,
        reverse_charge=invoice.reverse_charge,
        withholding=invoice.withholding_rate,
        guarantee=invoice.guarantee_rate,
    )
    p = data.professional
    notes = [
        note
        for note in (
            _vat_note(correct),
            (
                f"Forma de pago: transferencia bancaria a la cuenta {p.iban} antes del "
                f"{date_slash(invoice.due_date)}."
            ),
        )
        if note
    ]
    if invoice.guarantee_rate is not None:
        notes.append(
            f"Retención de garantía del {es_percent(invoice.guarantee_rate)} % de la base, "
            "pagadera al terminar el plazo de garantía de la obra.",
        )
    references: tuple[str, ...] = ()
    if invoice.quote_number is not None:
        references = (f"Según presupuesto {invoice.quote_number}",)
    return PrintedDocument(
        spec=spec,
        title="FACTURA",
        number_label="Factura n.º",
        number=invoice.number,
        issue_date=invoice.issue_date,
        valid_until=None,
        due_date=invoice.due_date,
        issuer=_issuer(data),
        issuer_trade_name=p.trade_name,
        issuer_activity=p.activity,
        issuer_town=_town(p.address),
        customer_label="Cliente",
        customer=_customer(spec, data, invoice.customer_key),
        subject=invoice.subject,
        references=references,
        lines=_lines(spec, invoice.lines, data, priced=True),
        priced=True,
        totals=printed,
        correct_totals=correct,
        notes=tuple(notes),
        iban=p.iban,
        signatory=None,
        paragraphs=(),
        registry=_registry(data),
        mentioned=(),
        omitted_customer_tax_id=_omitted_tax_id(spec, data, invoice.customer_key),
    )


def _from_quote(spec: DocumentSpec, quote: QuoteData, data: ProfessionalDataset) -> PrintedDocument:
    correct, printed = _totals(
        spec,
        quote.lines,
        reverse_charge=quote.reverse_charge,
        withholding=None,
        guarantee=None,
    )
    p = data.professional
    notes = [
        note
        for note in (
            _vat_note(correct),
            f"Presupuesto válido hasta el {date_slash(quote.valid_until)}.",
            "Forma de pago: 40 % al aceptar el presupuesto y el resto al terminar el trabajo.",
            "Cualquier trabajo no incluido en este presupuesto se valorará aparte.",
            "Aceptado por el cliente (fecha y firma):",
        )
        if note
    ]
    return PrintedDocument(
        spec=spec,
        title="PRESUPUESTO",
        number_label="Presupuesto n.º",
        number=quote.number,
        issue_date=quote.issue_date,
        valid_until=quote.valid_until,
        due_date=None,
        issuer=_issuer(data),
        issuer_trade_name=p.trade_name,
        issuer_activity=p.activity,
        issuer_town=_town(p.address),
        customer_label="Cliente",
        customer=_customer(spec, data, quote.customer_key),
        subject=quote.subject,
        references=(),
        lines=_lines(spec, quote.lines, data, priced=True),
        priced=True,
        totals=printed,
        correct_totals=correct,
        notes=tuple(notes),
        iban=None,
        signatory=None,
        paragraphs=(),
        registry=_registry(data),
        mentioned=(),
    )


_OTHER_LABELS = {
    OtherKind.SUPPLIER_DELIVERY_NOTE: ("Albarán n.º", "Entregar a"),
    OtherKind.SUPPLIER_INVOICE: ("Factura n.º", "Cliente"),
    OtherKind.COMMUNITY_LETTER: ("Referencia", "Destinatario"),
    OtherKind.PURCHASE_ORDER: ("Pedido n.º", "Subcontratista"),
    OtherKind.WORK_REPORT: ("Parte n.º", "Cliente"),
}


def _from_other(
    spec: DocumentSpec,
    other: OtherDocumentData,
    data: ProfessionalDataset,
) -> PrintedDocument:
    number_label, customer_label = _OTHER_LABELS[other.kind]
    totals = None
    if other.priced and other.vat_rate is not None:
        totals = compute_totals(
            other.lines,
            reverse_charge=False,
            withholding_rate=None,
            guarantee_rate=None,
        )
    mentioned = tuple(
        PartyData(name=c.name, tax_id=None, address=c.address)
        for c in data.customers
        if other.kind is OtherKind.COMMUNITY_LETTER and c.name == other.reference
    )
    is_own = other.issuer.name == data.professional.name
    notes = other.paragraphs
    if other.signatory is not None and other.kind is not OtherKind.COMMUNITY_LETTER:
        notes = (*notes, f"Fdo.: {other.signatory}, jefe de obra.")
    return PrintedDocument(
        spec=spec,
        title=other.title,
        number_label=number_label,
        number=other.reference,
        issue_date=other.issue_date,
        valid_until=None,
        due_date=None,
        issuer=other.issuer,
        issuer_trade_name=data.professional.trade_name if is_own else None,
        issuer_activity=data.professional.activity if is_own else None,
        issuer_town=_town(other.issuer.address),
        customer_label=customer_label,
        customer=other.recipient,
        subject=None,
        references=(),
        lines=_lines(spec, other.lines, data, priced=other.priced),
        priced=other.priced,
        totals=totals,
        correct_totals=totals,
        notes=notes,
        iban=None,
        signatory=other.signatory,
        paragraphs=other.paragraphs,
        registry=None,
        mentioned=mentioned,
    )
