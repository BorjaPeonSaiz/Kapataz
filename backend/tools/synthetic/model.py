"""Tipos del dataset sintético: datos puros, sin E/S (ADR-020).

Correspondencia con el dominio, para ``seed_demo.py``:

- ``ProfessionalData`` → ``Professional(name, TaxId(tax_id), address)``.
- ``CustomerData`` → ``Customer(name, TaxId(tax_id), address)``. ``since`` es
  la fecha de alta: ``created_at`` sale de ella con la zona que elija quien carga.
- ``CatalogEntryData`` → ``CatalogItem(concept, unit, Money(reference_price),
  CatalogItemOrigin.MANUAL, is_material)``.
- ``QuoteData`` → ``Quote(number=DocumentNumber.parse(number), status, versions=
  (QuoteVersion(lines, recipient_type, dwelling_over_two_years, valid_until),))``.
- ``LineData`` → ``QuoteLine(description, Quantity(quantity), Money(unit_price),
  PriceSource, Percentage(discount) si hay, is_material, outside_works)``. La
  unidad no existe en la línea del dominio: solo la lleva el catálogo
  (``catalog_key``), y el documento la imprime.

Las facturas (``InvoiceData``) no se cargan como facturas emitidas: son el
histórico importado (RF-IN-09) y llegan como documentos en el Bloque 4.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from kapataz.domain.billing.calculation import line_base
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.quote import QuoteStatus


class Trade(StrEnum):
    """Profesional ficticio. El valor es el nombre de su carpeta en ``samples/``."""

    ELECTRICIAN = "electricista"
    BRICKLAYER = "albanil"


class DocumentType(StrEnum):
    """Clasificación esperada del documento (RF-IN-02)."""

    INVOICE = "factura"
    QUOTE = "presupuesto"
    OTHER = "otro"


class Layout(StrEnum):
    """Maquetación del PDF. ``carta`` solo la usan algunos documentos «otro»."""

    CLASSIC_TABLE = "tabla_clasica"
    WORD_EXPORT = "word_exportado"
    GENERIC_SOFTWARE = "programa_generico"
    PLAIN_TEXT = "texto_sin_tabla"
    LOGO_LONG_FOOTER = "logotipo_pie_extenso"
    LETTER = "carta"


# Las cinco maquetaciones de ADR-020, en las que se reparten facturas y presupuestos.
MAIN_LAYOUTS = (
    Layout.CLASSIC_TABLE,
    Layout.WORD_EXPORT,
    Layout.GENERIC_SOFTWARE,
    Layout.PLAIN_TEXT,
    Layout.LOGO_LONG_FOOTER,
)


class SeededErrorKind(StrEnum):
    """Imperfección sembrada a propósito en un documento."""

    TOTAL_MISMATCH = "total_no_cuadra"
    BASE_MISMATCH = "base_no_cuadra"
    VAT_MISMATCH = "cuota_iva_no_cuadra"
    MISSING_TAX_ID = "nif_ausente"
    SPLIT_LINE = "linea_partida"


class ReviewReason(StrEnum):
    """Motivo por el que la ingesta debe dejar el documento en revisión (RF-IN-05)."""

    TOTAL_MISMATCH = "total_no_cuadra"
    BASE_MISMATCH = "base_no_cuadra"
    VAT_MISMATCH = "cuota_iva_no_cuadra"
    MISSING_CUSTOMER_TAX_ID = "falta_nif_cliente"


class TrapTechnique(StrEnum):
    """Cómo se esconde la instrucción inyectada en el PDF trampa (RN-05, ADR-019).

    El pie visible también se usa en un PDF escaneado: ahí la instrucción solo
    está en la imagen y llega por la ruta de OCR. En los metadatos, va en el
    ``/Subject`` del PDF y no se ve en ninguna página.
    """

    VISIBLE_FOOTER = "pie_visible"
    HIDDEN_TEXT = "texto_oculto"
    LINE_CONCEPT = "concepto_de_linea"
    METADATA = "metadatos"


class OtherKind(StrEnum):
    """Documento que no es factura emitida ni presupuesto (RF-IN-02)."""

    SUPPLIER_DELIVERY_NOTE = "albaran_proveedor"
    SUPPLIER_INVOICE = "factura_proveedor"
    COMMUNITY_LETTER = "carta_comunidad"
    PURCHASE_ORDER = "hoja_de_pedido"
    WORK_REPORT = "parte_de_trabajo"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfessionalData:
    """Autónomo ficticio que emite los documentos."""

    trade: Trade
    name: str
    trade_name: str
    activity: str
    tax_id: str
    address: str
    phone: str
    email: str
    iban: str
    invoice_series: str
    quote_series: str

    @property
    def slug(self) -> str:
        return self.trade.value


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerData:
    """Cliente. ``is_contractor``: constructora o promotora, con inversión del sujeto pasivo."""

    key: str
    name: str
    tax_id: str
    address: str
    recipient_type: RecipientType
    is_contractor: bool
    since: date


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogEntryData:
    """Concepto del catálogo de referencia del profesional (RF-CF-02)."""

    key: str
    concept: str
    detail: str
    unit: str
    reference_price: Decimal
    is_material: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class LineData:
    """Línea de presupuesto o de factura tal como la escribe el profesional.

    ``vat_rate`` es el tipo de la línea en el documento (10 o 21); es None con
    inversión del sujeto pasivo. Un documento del histórico puede mezclar dos
    tipos: la obra al reducido y lo que se vende fuera de ella al general.
    """

    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount: Decimal | None
    is_material: bool
    outside_works: bool
    catalog_key: str | None
    vat_rate: Decimal | None

    @property
    def amount(self) -> Decimal:
        """Base de la línea con la regla del dominio: un solo redondeo (RN-03)."""
        discount = None if self.discount is None else Percentage(self.discount)
        return line_base(Quantity(self.quantity), Money(self.unit_price), discount).amount


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteData:
    """Presupuesto con una sola versión, en su estado al final del periodo."""

    number: str
    customer_key: str
    issue_date: date
    valid_until: date
    status: QuoteStatus
    recipient_type: RecipientType
    dwelling_over_two_years: bool | None
    subject: str
    lines: tuple[LineData, ...]
    reverse_charge: bool
    detailed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceData:
    """Factura del histórico del profesional (RF-IN-09).

    ``withholding_rate`` es la retención de IRPF y ``guarantee_rate`` la
    retención de garantía, los dos en porcentaje sobre la base.
    """

    number: str
    customer_key: str
    issue_date: date
    due_date: date
    subject: str
    lines: tuple[LineData, ...]
    reverse_charge: bool
    withholding_rate: Decimal | None
    guarantee_rate: Decimal | None
    quote_number: str | None
    recipient_type: RecipientType
    dwelling_over_two_years: bool | None
    detailed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PartyData:
    """Parte de un documento «otro»: proveedor, administrador, constructora…"""

    name: str
    tax_id: str | None
    address: str
    phone: str | None = None
    email: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class OtherDocumentData:
    """Documento que no es factura emitida ni presupuesto del profesional (RF-IN-02).

    ``lines`` lleva precio solo si el documento lo imprime (``priced``).
    ``paragraphs`` es el cuerpo de una carta o las observaciones.
    """

    kind: OtherKind
    title: str
    reference: str
    issue_date: date
    issuer: PartyData
    recipient: PartyData
    signatory: str | None
    lines: tuple[LineData, ...]
    priced: bool
    vat_rate: Decimal | None
    paragraphs: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TrapData:
    """Instrucción inyectada en un PDF con apariencia de factura (RN-05, ADR-019)."""

    technique: TrapTechnique
    injected_text: str
    line_index: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentSpec:
    """Qué PDF se genera: de qué dato sale, con qué maquetación y con qué imperfección.

    Exactamente uno de ``invoice``, ``quote`` y ``other`` está informado,
    según ``document_type``. ``error_variant`` elige cómo se comete el error
    sembrado; ``scan_seed`` alimenta el ruido del escaneado.
    """

    doc_id: str
    trade: Trade
    document_type: DocumentType
    layout: Layout
    scanned: bool
    scan_seed: int
    invoice: InvoiceData | None
    quote: QuoteData | None
    other: OtherDocumentData | None
    seeded_error: SeededErrorKind | None
    error_variant: int
    trap: TrapData | None

    @property
    def issue_date(self) -> date:
        if self.invoice is not None:
            return self.invoice.issue_date
        if self.quote is not None:
            return self.quote.issue_date
        if self.other is not None:
            return self.other.issue_date
        raise AssertionError("Un documento sale de una factura, un presupuesto u otro.")

    @property
    def lines(self) -> tuple[LineData, ...]:
        if self.invoice is not None:
            return self.invoice.lines
        if self.quote is not None:
            return self.quote.lines
        if self.other is not None:
            return self.other.lines
        raise AssertionError("Un documento sale de una factura, un presupuesto u otro.")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfessionalDataset:
    """Todo lo de un profesional: emisor, clientes, catálogo, actividad y documentos."""

    professional: ProfessionalData
    customers: tuple[CustomerData, ...]
    catalog: tuple[CatalogEntryData, ...]
    quotes: tuple[QuoteData, ...]
    invoices: tuple[InvoiceData, ...]
    documents: tuple[DocumentSpec, ...]

    def customer(self, key: str) -> CustomerData:
        for customer in self.customers:
            if customer.key == key:
                return customer
        raise KeyError(key)


@dataclass(frozen=True, slots=True, kw_only=True)
class SyntheticDataset:
    """Resultado de ``build_dataset``: dos profesionales en un periodo fijo de 18 meses."""

    seed: int
    period_start: date
    period_end: date
    professionals: tuple[ProfessionalDataset, ...]

    def professional(self, trade: Trade) -> ProfessionalDataset:
        for item in self.professionals:
            if item.professional.trade is trade:
                return item
        raise KeyError(trade)
