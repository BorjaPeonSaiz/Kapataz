"""Las cinco maquetaciones de ADR-020 y la carta de los documentos «otro».

- ``tabla_clasica``: cuadrícula completa, caja de datos y totales en recuadro.
- ``word_exportado``: cabecera centrada, tabla solo con filetes y fecha en letra.
- ``programa_generico``: banda gris, códigos de artículo, filas cebreadas e
  importes sin símbolo de euro, con el cuadro de impuestos al pie.
- ``texto_sin_tabla``: carta con las líneas redactadas y los importes en letra
  de párrafo, sin separador de miles.
- ``logotipo_pie_extenso``: logotipo dibujado con formas simples, colores y un
  pie largo con datos registrales, cuenta y protección de datos.
"""

from collections.abc import Callable
from decimal import Decimal

from synthetic.amounts import Totals
from synthetic.formats import (
    date_dash,
    date_dot,
    date_long,
    date_slash,
    es_amount,
    es_percent,
    es_plain_amount,
    es_quantity,
)
from synthetic.model import Layout as LayoutName
from synthetic.model import Trade
from synthetic.pdfkit import (
    BOLD,
    GRAY,
    ITALIC,
    LIGHT,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    REGULAR,
    RGB,
    WHITE,
    Column,
    Layout,
    Painter,
    wrap,
)
from synthetic.printed import PrintedDocument, PrintedLine

type Money = Callable[[Decimal], str]
type TotalsRow = tuple[str, str, bool]

_LONG_TITLE = 20


def party_lines(
    doc: PrintedDocument, *, customer: bool, width: float, size: float = 9
) -> list[str]:
    """Nombre, NIF y domicilio de una parte; sin NIF si el documento no lo lleva."""
    party = doc.customer if customer else doc.issuer
    lines = [party.name]
    if party.tax_id is not None:
        lines.append(f"NIF: {party.tax_id}")
    lines.extend(wrap(party.address, width, size=size))
    return lines


def contact_lines(doc: PrintedDocument) -> list[str]:
    issuer = doc.issuer
    lines: list[str] = []
    if issuer.phone:
        lines.append(f"Tel. {issuer.phone}")
    if issuer.email:
        lines.append(issuer.email)
    return lines


def printed_totals(doc: PrintedDocument) -> Totals:
    """Los importes impresos; solo se piden en documentos que los tienen."""
    if doc.totals is None:
        msg = f"{doc.spec.doc_id} no tiene importes que imprimir."
        raise ValueError(msg)
    return doc.totals


def total_label(doc: PrintedDocument) -> str:
    return f"TOTAL {doc.title}" if len(doc.title) <= _LONG_TITLE else "TOTAL"


def totals_rows(totals: Totals, money: Money, *, total: str) -> list[TotalsRow]:
    """Filas de totales comunes: base, IVA (con desglose si hay varios tipos), retenciones."""
    rows: list[TotalsRow] = [("Base imponible", money(totals.base), False)]
    if totals.reverse_charge:
        rows.append(("IVA (inversión del sujeto pasivo)", money(Decimal("0.00")), False))
    elif len(totals.buckets) == 1 and totals.buckets[0].rate is not None:
        rows.append(
            (f"IVA {es_percent(totals.buckets[0].rate)} %", money(totals.vat_amount), False)
        )
    else:
        for bucket in totals.buckets:
            rate = es_percent(bucket.rate or Decimal(0))
            rows.append((f"IVA {rate} % s/ {money(bucket.base)}", money(bucket.amount), False))
    if totals.withholding is not None and totals.withholding_rate is not None:
        label = f"Retención IRPF {es_percent(totals.withholding_rate)} %"
        rows.append((label, f"-{money(totals.withholding)}", False))
    rows.append((total, money(totals.total), True))
    if totals.guarantee is not None and totals.guarantee_rate is not None:
        label = f"Retención de garantía {es_percent(totals.guarantee_rate)} %"
        rows.append((label, f"-{money(totals.guarantee)}", False))
        rows.append(("Líquido a percibir", money(totals.amount_due), True))
    return rows


def _euros(value: Decimal) -> str:
    return f"{es_amount(value)} €"


class _TableLayout(Layout):
    """Base de las maquetaciones con tabla: celdas y columnas comunes."""

    def money(self, value: Decimal) -> str:
        return _euros(value)

    quantity_with_unit = False

    def cells(
        self, doc: PrintedDocument, line: PrintedLine, columns: list[Column]
    ) -> dict[str, list[str]]:
        del doc
        values: dict[str, list[str]] = {}
        for column in columns:
            values[column.key] = self.cell(line, column)
        return values

    def cell(self, line: PrintedLine, column: Column) -> list[str]:  # noqa: PLR0911 - una por columna
        match column.key:
            case "description":
                return wrap(line.description, column.width - 8, size=self.row_size)
            case "code":
                return [line.code]
            case "quantity":
                quantity = es_quantity(line.quantity)
                return [f"{quantity} {line.unit}" if self.quantity_with_unit else quantity]
            case "unit":
                return [line.unit]
            case "unit_price":
                return [self.money(line.unit_price)] if line.unit_price is not None else [""]
            case "discount":
                return [f"{es_percent(line.discount)} %"] if line.discount is not None else [""]
            case "vat":
                return [f"{es_percent(line.vat_rate)} %"] if line.vat_rate is not None else [""]
            case "amount":
                return [self.money(line.amount)] if line.amount is not None else [""]
            case _:
                return [""]

    def cell_texts(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        *,
        color: RGB = (0.0, 0.0, 0.0),
    ) -> None:
        x = self.left
        for column in columns:
            values = cells.get(column.key, [])
            if column.align == "right":
                anchor = x + column.width - 4
            elif column.align == "center":
                anchor = x + column.width / 2
            else:
                anchor = x + 4
            p.lines(
                anchor,
                y - 10,
                values,
                leading=self.row_leading,
                size=self.row_size,
                align=column.align,
                color=color,
            )
            x += column.width

    def header_texts(self, p: Painter, y: float, columns: list[Column], *, color: RGB) -> None:
        x = self.left
        for column in columns:
            if column.align == "right":
                anchor = x + column.width - 4
            elif column.align == "center":
                anchor = x + column.width / 2
            else:
                anchor = x + 4
            p.text(
                anchor, y - 11, column.title, font=BOLD, size=7.5, color=color, align=column.align
            )
            x += column.width


def _priced_columns(
    doc: PrintedDocument,
    *,
    description: float,
    quantity: float,
    unit: float | None,
    price: float,
    discount: float,
    amount: float,
    titles: dict[str, str],
    code: float | None = None,
    vat: float = 36,
) -> list[Column]:
    """Columnas de una tabla con precios; con varios tipos de IVA, la columna del tipo."""
    if doc.multi_rate:
        description -= vat
    columns: list[Column] = []
    if code is not None:
        columns.append(Column("code", titles.get("code", "Código"), code))
    columns.append(Column("description", titles.get("description", "Concepto"), description))
    columns.append(Column("quantity", titles.get("quantity", "Cant."), quantity, "right"))
    if unit is not None:
        columns.append(Column("unit", titles.get("unit", "Ud."), unit, "center"))
    columns.append(Column("unit_price", titles.get("unit_price", "Precio"), price, "right"))
    columns.append(Column("discount", titles.get("discount", "Dto."), discount, "right"))
    if doc.multi_rate:
        columns.append(Column("vat", titles.get("vat", "IVA"), vat, "right"))
    columns.append(Column("amount", titles.get("amount", "Importe"), amount, "right"))
    return columns


# ------------------------------------------------------------------ tabla clásica


class ClassicTable(_TableLayout):
    name = LayoutName.CLASSIC_TABLE

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        top = PAGE_HEIGHT - 52
        p.text(self.left, top, doc.issuer.name, font=BOLD, size=12.5)
        info = party_lines(doc, customer=False, width=250, size=8.5)[1:] + contact_lines(doc)
        y = p.lines(self.left, top - 15, info, leading=10.5, size=8.5)
        size = 16 if len(doc.title) <= _LONG_TITLE else 11
        p.text(self.right, top, doc.title, font=BOLD, size=size, align="right")
        meta = [(doc.number_label, doc.number), ("Fecha", date_slash(doc.issue_date))]
        if doc.valid_until is not None:
            meta.append(("Válido hasta", date_slash(doc.valid_until)))
        if doc.due_date is not None:
            meta.append(("Vencimiento", date_slash(doc.due_date)))
        box_x, box_w = self.right - 210, 210.0
        box_top = top - 12
        p.rect(box_x, box_top - 14 * len(meta) - 4, box_w, 14 * len(meta) + 4)
        for index, (label, value) in enumerate(meta):
            row_y = box_top - 13 - 14 * index
            p.text(box_x + 6, row_y, label, size=8.5, color=GRAY)
            p.text(box_x + box_w - 6, row_y, value, font=BOLD, size=8.5, align="right")
        y = min(y, box_top - 14 * len(meta) - 4) - 14
        customer = party_lines(doc, customer=True, width=300)
        height = 18 + 11 * len(customer)
        p.rect(self.left, y - height, 320, height)
        p.text(self.left + 6, y - 11, doc.customer_label.upper(), font=BOLD, size=7.5, color=GRAY)
        p.lines(self.left + 6, y - 24, customer, leading=11, size=9)
        y -= height + 14
        for extra in ([f"Trabajo: {doc.subject}"] if doc.subject else []) + list(doc.references):
            p.text(self.left, y, extra, size=9)
            y -= 13
        return y - 4

    def columns(self, doc: PrintedDocument) -> list[Column]:
        if not doc.priced:
            return [
                Column("description", "Concepto", 330),
                Column("quantity", "Cantidad", 85, "right"),
                Column("unit", "Unidad", 90, "center"),
            ]
        return _priced_columns(
            doc,
            description=235,
            quantity=45,
            unit=35,
            price=65,
            discount=40,
            amount=85,
            titles={},
        )

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        p.rect(self.left, y - 16, self.width, 16, fill=LIGHT)
        self._verticals(p, y, 16, columns)
        self.header_texts(p, y, columns, color=(0.0, 0.0, 0.0))
        return y - 16

    def _verticals(self, p: Painter, y: float, height: float, columns: list[Column]) -> None:
        x = self.left
        p.c.setLineWidth(0.5)
        for column in columns:
            p.c.line(x, y, x, y - height)
            x += column.width
        p.c.line(x, y, x, y - height)

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        del index
        self.cell_texts(p, y, columns, cells)
        self._verticals(p, y, height, columns)
        p.hline(self.left, self.right, y - height)

    def totals_height(self, doc: PrintedDocument) -> float:
        return 14.0 * len(self._rows(doc)) + 20

    def _rows(self, doc: PrintedDocument) -> list[TotalsRow]:
        return totals_rows(printed_totals(doc), self.money, total=total_label(doc))

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        rows = self._rows(doc)
        y -= 10
        box_x = self.right - 230
        p.rect(box_x, y - 14 * len(rows) - 4, 230, 14 * len(rows) + 4)
        for index, (label, value, bold) in enumerate(rows):
            row_y = y - 13 - 14 * index
            font = BOLD if bold else REGULAR
            p.text(box_x + 6, row_y, label, font=font, size=8.5)
            p.text(self.right - 6, row_y, value, font=font, size=8.5, align="right")
        return y - 14 * len(rows) - 12

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        del doc
        p.text(
            self.left + self.width / 2,
            40,
            f"Página {page} de {pages}",
            size=7.5,
            color=GRAY,
            align="center",
        )


# ------------------------------------------------------------------ Word exportado


class WordExport(_TableLayout):
    name = LayoutName.WORD_EXPORT
    quantity_with_unit = True
    row_size = 9.0
    row_leading = 11.5

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        center = self.left + self.width / 2
        y = PAGE_HEIGHT - 55
        p.text(center, y, doc.issuer.name, font=BOLD, size=14, align="center")
        details = [f"NIF {doc.issuer.tax_id}" if doc.issuer.tax_id else "", doc.issuer.address]
        y = p.lines(
            center,
            y - 16,
            [" · ".join(d for d in details if d)],
            leading=11,
            size=8.5,
            align="center",
        )
        contact = " · ".join(contact_lines(doc))
        if contact:
            y = p.lines(center, y, [contact], leading=11, size=8.5, align="center")
        p.hline(self.left, self.right, y + 3)
        y -= 16
        p.text(self.left, y, doc.title, font=BOLD, size=12)
        y -= 16
        rows = [f"{doc.number_label.replace('n.º', 'número').capitalize()}: {doc.number}"]
        rows.append(f"Fecha: {date_long(doc.issue_date)}")
        if doc.valid_until is not None:
            rows.append(f"Válido hasta: {date_long(doc.valid_until)}")
        if doc.due_date is not None:
            rows.append(f"Vencimiento: {date_long(doc.due_date)}")
        y = p.lines(self.left, y, rows, leading=12, size=9.5)
        y -= 6
        p.text(self.left, y, f"Datos del {doc.customer_label.lower()}:", font=BOLD, size=9.5)
        y = p.lines(
            self.left,
            y - 13,
            party_lines(doc, customer=True, width=400, size=9.5),
            leading=12,
            size=9.5,
        )
        if doc.subject:
            y -= 4
            y = p.lines(
                self.left,
                y,
                wrap(f"Descripción del trabajo: {doc.subject}", self.width, size=9.5),
                leading=12,
                size=9.5,
            )
        for reference in doc.references:
            y = p.lines(self.left, y, [reference], leading=12, size=9.5)
        return y - 8

    def columns(self, doc: PrintedDocument) -> list[Column]:
        if not doc.priced:
            return [
                Column("description", "Descripción", 355),
                Column("quantity", "Cantidad", 150, "right"),
            ]
        return _priced_columns(
            doc,
            description=255,
            quantity=70,
            unit=None,
            price=70,
            discount=45,
            amount=65,
            titles={
                "description": "Descripción",
                "quantity": "Cantidad",
                "unit_price": "Precio unit.",
                "discount": "Dto.",
                "amount": "Total",
            },
        )

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        p.hline(self.left, self.right, y, width=0.8)
        self.header_texts(p, y, columns, color=(0.0, 0.0, 0.0))
        p.hline(self.left, self.right, y - 16, width=0.8)
        return y - 18

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        del index, height
        self.cell_texts(p, y, columns, cells)

    def totals_height(self, doc: PrintedDocument) -> float:
        return 13.0 * len(self._rows(doc)) + 24

    def _rows(self, doc: PrintedDocument) -> list[TotalsRow]:
        rows = totals_rows(printed_totals(doc), self.money, total="Total")
        return [
            ("Suma" if label == "Base imponible" else label, value, bold)
            for label, value, bold in rows
        ]

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        p.hline(self.left, self.right, y - 2, width=0.8)
        y -= 18
        for label, value, bold in self._rows(doc):
            font = BOLD if bold else REGULAR
            p.text(self.right - 95, y, f"{label}:", font=font, size=9.5, align="right")
            p.text(self.right, y, value, font=font, size=9.5, align="right")
            y -= 13
        return y - 4

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        del doc
        if pages > 1:
            p.text(self.left + self.width / 2, 36, str(page), size=9, align="center")


# ------------------------------------------------------------------ programa genérico

_BAND: RGB = (0.27, 0.31, 0.36)
_ZEBRA: RGB = (0.94, 0.95, 0.96)


class GenericSoftware(_TableLayout):
    name = LayoutName.GENERIC_SOFTWARE

    def money(self, value: Decimal) -> str:
        return es_amount(value)

    row_size = 8.0
    row_leading = 10.0

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        top = PAGE_HEIGHT - 40
        p.rect(0, top - 38, PAGE_WIDTH, 38, fill=_BAND, stroke=None)
        p.text(self.left, top - 25, doc.title, font=BOLD, size=15, color=WHITE)
        p.text(
            self.right,
            top - 25,
            doc.issuer_trade_name or doc.issuer.name,
            font=BOLD,
            size=9,
            color=WHITE,
            align="right",
        )
        y = top - 56
        issuer = party_lines(doc, customer=False, width=230, size=8) + contact_lines(doc)
        p.text(self.left, y, "Emisor", font=BOLD, size=7.5, color=GRAY)
        p.lines(self.left, y - 11, issuer, leading=10, size=8)
        box_x = self.left + 270
        customer = party_lines(doc, customer=True, width=215, size=8)
        height = 16 + 10 * len(customer)
        p.c.setLineWidth(0.5)
        p.c.roundRect(box_x, y + 8 - height, self.right - box_x, height, 4, stroke=1, fill=0)
        label = "Facturar a" if doc.title == "FACTURA" else doc.customer_label
        p.text(box_x + 6, y - 2, label, font=BOLD, size=7.5, color=GRAY)
        p.lines(box_x + 6, y - 13, customer, leading=10, size=8)
        y -= max(11 + 10 * len(issuer), height) + 6
        cells = [(doc.number_label.replace(" n.º", "").replace("Factura", "Número"), doc.number)]
        cells.append(("Fecha", date_dash(doc.issue_date)))
        cells.append(("Cód. cliente", f"CLI-{sum(map(ord, doc.customer.name)) % 1000:04d}"))
        if doc.due_date is not None:
            cells.append(("Vencimiento", date_dash(doc.due_date)))
        elif doc.valid_until is not None:
            cells.append(("Validez", date_dash(doc.valid_until)))
        width = self.width / len(cells)
        for index, (label, value) in enumerate(cells):
            x = self.left + width * index
            p.rect(x, y - 26, width, 26)
            p.text(x + 4, y - 9, label, size=6.5, color=GRAY)
            p.text(x + 4, y - 21, value, font=BOLD, size=8.5)
        y -= 40
        for extra in ([f"Obra: {doc.subject}"] if doc.subject else []) + list(doc.references):
            p.text(self.left, y, extra, size=8)
            y -= 11
        return y - 4

    def columns(self, doc: PrintedDocument) -> list[Column]:
        if not doc.priced:
            return [
                Column("code", "Código", 60),
                Column("description", "Descripción", 325),
                Column("quantity", "Cantidad", 60, "right"),
                Column("unit", "Unidad", 60, "center"),
            ]
        return _priced_columns(
            doc,
            code=50,
            description=215,
            quantity=55,
            unit=None,
            price=60,
            discount=40,
            amount=85,
            titles={
                "description": "Descripción",
                "quantity": "Cantidad",
                "discount": "% Dto.",
                "vat": "% IVA",
                "amount": "Importe (EUR)",
            },
        )

    def cell(self, line: PrintedLine, column: Column) -> list[str]:
        if column.key == "quantity":
            return [es_quantity(line.quantity, decimals=2)]
        return super().cell(line, column)

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        p.rect(self.left, y - 16, self.width, 16, fill=_BAND, stroke=None)
        self.header_texts(p, y, columns, color=WHITE)
        return y - 16

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        if index % 2 == 1:
            p.rect(self.left, y - height, self.width, height, fill=_ZEBRA, stroke=None)
        self.cell_texts(p, y, columns, cells)

    def _table(self, doc: PrintedDocument) -> tuple[list[str], list[list[str]], list[TotalsRow]]:
        totals = printed_totals(doc)
        heads = ["Base imponible", "% IVA", "Cuota IVA"]
        if totals.withholding is not None:
            heads += ["% IRPF", "Retención"]
        rows: list[list[str]] = []
        for bucket in totals.buckets:
            rate = "ISP" if bucket.rate is None else es_percent(bucket.rate)
            row = [es_amount(bucket.base), rate, es_amount(bucket.amount)]
            if totals.withholding is not None and totals.withholding_rate is not None:
                row += [es_percent(totals.withholding_rate), es_amount(totals.withholding)]
            rows.append(row)
        extra: list[TotalsRow] = [(f"{total_label(doc)} (EUR)", es_amount(totals.total), True)]
        if totals.guarantee is not None and totals.guarantee_rate is not None:
            extra.append(
                (
                    f"Retención de garantía {es_percent(totals.guarantee_rate)} %",
                    es_amount(totals.guarantee),
                    False,
                )
            )
            extra.append(("Líquido a percibir (EUR)", es_amount(totals.amount_due), True))
        return heads, rows, extra

    def totals_height(self, doc: PrintedDocument) -> float:
        _, rows, extra = self._table(doc)
        return 16.0 + 13 * len(rows) + 16 * len(extra) + 14

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        heads, rows, extra = self._table(doc)
        y -= 10
        width = self.width / len(heads)
        p.rect(self.left, y - 14, self.width, 14, fill=LIGHT)
        for index, head in enumerate(heads):
            p.text(
                self.left + width * (index + 1) - 4, y - 10, head, font=BOLD, size=7, align="right"
            )
        y -= 14
        for row in rows:
            p.rect(self.left, y - 13, self.width, 13)
            for index, value in enumerate(row):
                p.text(self.left + width * (index + 1) - 4, y - 9.5, value, size=8, align="right")
            y -= 13
        y -= 4
        for label, value, bold in extra:
            font = BOLD if bold else REGULAR
            if bold:
                p.rect(self.right - 220, y - 15, 220, 15, fill=LIGHT)
            p.text(self.right - 214, y - 11, label, font=font, size=8.5)
            p.text(self.right - 4, y - 11, value, font=font, size=8.5, align="right")
            y -= 16
        return y - 4

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        del doc
        p.hline(self.left, self.right, 48, color=GRAY, width=0.3)
        p.text(
            self.left, 38, "Gestión comercial v4.2 · Copia para el cliente", size=6.5, color=GRAY
        )
        p.text(self.right, 38, f"Página {page}/{pages}", size=6.5, color=GRAY, align="right")


# ------------------------------------------------------------------ texto sin tabla


def _plain_money(value: Decimal) -> str:
    return f"{es_plain_amount(value)} euros"


class PlainText(_TableLayout):
    name = LayoutName.PLAIN_TEXT

    def money(self, value: Decimal) -> str:
        return _plain_money(value)

    row_size = 9.5
    row_leading = 12.5
    row_padding = 3.0

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        y = PAGE_HEIGHT - 55
        p.text(self.left, y, doc.issuer.name, font=BOLD, size=10.5)
        info = party_lines(doc, customer=False, width=300, size=9.5)[1:]
        contact = " · ".join(contact_lines(doc))
        y = p.lines(
            self.left, y - 14, [*info, *([contact] if contact else [])], leading=12, size=9.5
        )
        y -= 14
        p.text(
            self.right,
            y,
            f"{doc.issuer_town}, a {date_long(doc.issue_date)}",
            size=9.5,
            align="right",
        )
        y -= 26
        p.text(self.left, y, f"{doc.title} N.º {doc.number}", font=BOLD, size=11)
        y -= 18
        customer = doc.customer
        nif = f", con NIF {customer.tax_id}," if customer.tax_id else ""
        sentence = f"{doc.customer_label}: {customer.name}{nif} y domicilio en {customer.address}."
        y = p.lines(self.left, y, wrap(sentence, self.width, size=9.5), leading=12.5, size=9.5)
        extra = []
        if doc.subject:
            extra.append(f"Asunto: {doc.subject}.")
        extra.extend(f"{reference}." for reference in doc.references)
        if doc.valid_until is not None:
            extra.append(f"Este presupuesto es válido hasta el {date_long(doc.valid_until)}.")
        for text in extra:
            y = p.lines(self.left, y, wrap(text, self.width, size=9.5), leading=12.5, size=9.5)
        y -= 8
        p.text(self.left, y, "Detalle de los trabajos:", font=BOLD, size=9.5)
        return y - 6

    def columns(self, doc: PrintedDocument) -> list[Column]:
        del doc
        return [Column("description", "", self.width)]

    def cells(
        self, doc: PrintedDocument, line: PrintedLine, columns: list[Column]
    ) -> dict[str, list[str]]:
        quantity = f"{es_quantity(line.quantity)} {line.unit}"
        # Un concepto que ya acaba en punto no lleva además los dos puntos.
        lead = f"- {line.description}" + (" " if line.description.endswith(".") else ": ")
        if line.unit_price is None or line.amount is None:
            sentence = f"{lead}{quantity}."
        else:
            parts = [f"{lead}{quantity} a {self.money(line.unit_price)}"]
            if line.discount is not None:
                parts.append(f", con un descuento del {es_percent(line.discount)} %")
            if doc.multi_rate and line.vat_rate is not None:
                parts.append(f" (IVA del {es_percent(line.vat_rate)} %)")
            parts.append(f"; importe, {self.money(line.amount)}.")
            sentence = "".join(parts)
        return {"description": wrap(sentence, columns[0].width - 8, size=self.row_size)}

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        del p, columns
        return y

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        del index, height, columns
        p.lines(
            self.left + 6,
            y - 10,
            cells["description"],
            leading=self.row_leading,
            size=self.row_size,
        )

    def _sentences(self, doc: PrintedDocument) -> list[str]:
        totals = printed_totals(doc)
        sentences = [f"Base imponible: {self.money(totals.base)}."]
        if totals.reverse_charge:
            sentences.append("IVA: sin cuota, por inversión del sujeto pasivo.")
        elif len(totals.buckets) == 1 and totals.buckets[0].rate is not None:
            rate = es_percent(totals.buckets[0].rate)
            sentences.append(f"IVA al {rate} %: {self.money(totals.vat_amount)}.")
        else:
            for bucket in totals.buckets:
                rate = es_percent(bucket.rate or Decimal(0))
                sentences.append(
                    f"IVA al {rate} % sobre {self.money(bucket.base)}: {self.money(bucket.amount)}."
                )
        if totals.withholding is not None and totals.withholding_rate is not None:
            rate = es_percent(totals.withholding_rate)
            sentences.append(f"Retención de IRPF del {rate} %: -{self.money(totals.withholding)}.")
        what = "de la factura" if doc.title == "FACTURA" else "del presupuesto"
        sentences.append(f"Total {what}: {self.money(totals.total)}.")
        if totals.guarantee is not None and totals.guarantee_rate is not None:
            rate = es_percent(totals.guarantee_rate)
            sentences.append(
                f"Retención de garantía del {rate} %: {self.money(totals.guarantee)}. "
                f"Líquido a percibir: {self.money(totals.amount_due)}.",
            )
        return sentences

    def totals_height(self, doc: PrintedDocument) -> float:
        return 12.5 * len(self._sentences(doc)) + 30

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        y -= 10
        for sentence in self._sentences(doc):
            bold = sentence.startswith("Total")
            y = p.lines(
                self.left,
                y,
                wrap(sentence, self.width, size=9.5),
                leading=12.5,
                size=9.5,
                font=BOLD if bold else REGULAR,
            )
        return y - 4

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        del doc
        if pages > 1:
            p.text(self.right, 36, f"Pág. {page} de {pages}", size=8, align="right")


# ------------------------------------------------------------------ logotipo y pie extenso

_COLORS: dict[Trade, RGB] = {
    Trade.ELECTRICIAN: (0.11, 0.27, 0.53),
    Trade.BRICKLAYER: (0.64, 0.27, 0.18),
}
_ACCENT: dict[Trade, RGB] = {
    Trade.ELECTRICIAN: (0.98, 0.76, 0.12),
    Trade.BRICKLAYER: (0.85, 0.55, 0.38),
}


class LogoLongFooter(_TableLayout):
    name = LayoutName.LOGO_LONG_FOOTER
    base_footer = 72.0

    def _color(self, doc: PrintedDocument) -> RGB:
        return _COLORS[doc.spec.trade]

    def _logo(self, p: Painter, doc: PrintedDocument, x: float, y: float) -> None:
        """Logotipo con formas simples: un rayo en un círculo o un muro de ladrillo."""
        color, accent = self._color(doc), _ACCENT[doc.spec.trade]
        c = p.c
        if doc.spec.trade is Trade.ELECTRICIAN:
            c.setFillColorRGB(*color)
            c.circle(x + 26, y + 26, 26, stroke=0, fill=1)
            c.setFillColorRGB(*accent)
            bolt = c.beginPath()
            for index, (dx, dy) in enumerate(
                ((30, 48), (14, 24), (25, 24), (20, 4), (38, 30), (27, 30))
            ):
                if index == 0:
                    bolt.moveTo(x + dx, y + dy)
                else:
                    bolt.lineTo(x + dx, y + dy)
            bolt.close()
            c.drawPath(bolt, stroke=0, fill=1)
        else:
            for row in range(4):
                offset = 0 if row % 2 == 0 else 8
                for col in range(4):
                    fill = color if (row + col) % 2 == 0 else accent
                    c.setFillColorRGB(*fill)
                    c.rect(x + offset + col * 13, y + row * 13, 12, 11.5, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        color = self._color(doc)
        top = PAGE_HEIGHT - 40
        self._logo(p, doc, self.left, top - 56)
        p.text(
            self.left + 66,
            top - 24,
            doc.issuer_trade_name or doc.issuer.name,
            font=BOLD,
            size=16,
            color=color,
        )
        if doc.issuer_activity:
            p.text(self.left + 66, top - 38, doc.issuer_activity, font=ITALIC, size=8.5, color=GRAY)
        issuer = party_lines(doc, customer=False, width=190, size=8) + contact_lines(doc)
        p.lines(self.right, top - 8, issuer, leading=10, size=8, align="right")
        y = top - 18 - 10 * max(len(issuer), 5)
        p.rect(self.left, y - 24, self.width, 24, fill=color, stroke=None)
        p.text(
            self.left + 10,
            y - 16,
            f"{doc.title}   N.º {doc.number}",
            font=BOLD,
            size=11,
            color=WHITE,
        )
        p.text(
            self.right - 10,
            y - 16,
            f"Fecha: {date_dot(doc.issue_date)}",
            font=BOLD,
            size=10,
            color=WHITE,
            align="right",
        )
        y -= 40
        p.text(self.left, y, doc.customer_label, font=BOLD, size=8, color=color)
        left = p.lines(
            self.left,
            y - 12,
            party_lines(doc, customer=True, width=260, size=9),
            leading=11,
            size=9,
        )
        meta: list[str] = []
        if doc.due_date is not None:
            meta.append(f"Vencimiento: {date_dot(doc.due_date)}")
        if doc.valid_until is not None:
            meta.append(f"Validez: {date_dot(doc.valid_until)}")
        meta.extend(doc.references)
        if doc.subject:
            meta.extend(wrap(f"Obra: {doc.subject}", 200, size=8.5))
        right = p.lines(self.right, y - 12, meta, leading=11, size=8.5, align="right")
        return min(left, right) - 10

    def columns(self, doc: PrintedDocument) -> list[Column]:
        return _priced_columns(
            doc,
            description=250,
            quantity=45,
            unit=35,
            price=65,
            discount=35,
            amount=75,
            titles={"description": "Concepto"},
        )

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        p.rect(self.left, y - 16, self.width, 16, fill=(0.2, 0.2, 0.2), stroke=None)
        self.header_texts(p, y, columns, color=WHITE)
        return y - 16

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        del index
        self.cell_texts(p, y, columns, cells)
        p.hline(self.left, self.right, y - height, color=(0.75, 0.75, 0.75), width=0.4)

    def totals_height(self, doc: PrintedDocument) -> float:
        return 15.0 * len(totals_rows(printed_totals(doc), self.money, total="TOTAL")) + 20

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        y -= 12
        for label, value, bold in totals_rows(
            printed_totals(doc), self.money, total=total_label(doc)
        ):
            if bold:
                p.rect(self.right - 230, y - 15, 230, 15, fill=self._color(doc), stroke=None)
                p.text(self.right - 224, y - 11, label, font=BOLD, size=9, color=WHITE)
                p.text(self.right - 6, y - 11, value, font=BOLD, size=9, color=WHITE, align="right")
            else:
                p.text(self.right - 224, y - 11, label, size=8.5)
                p.text(self.right - 6, y - 11, value, size=8.5, align="right")
            y -= 15
        return y - 6

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        issuer = doc.issuer
        trade = doc.issuer_trade_name or issuer.name
        lines = [f"{trade} · {issuer.name} · NIF {issuer.tax_id} · {issuer.address}"]
        contact = " · ".join(contact_lines(doc))
        if doc.iban:
            contact += f" · Cuenta para transferencias: IBAN {doc.iban}"
        lines.append(contact)
        if doc.registry:
            lines.append(doc.registry + ".")
        privacy = (
            f"Protección de datos: el responsable del tratamiento es {issuer.name}. Sus datos "
            "se tratan para gestionar la relación comercial y la facturación, con base en el "
            "contrato y en las obligaciones legales, y no se ceden salvo obligación legal. "
            f"Puede ejercer sus derechos de acceso, rectificación, supresión y demás escribiendo "
            f"a {issuer.email}."
        )
        lines.extend(wrap(privacy, self.width - 40, size=6.3))
        p.hline(self.left, self.right, 32 + self.base_footer - 4, color=self._color(doc), width=0.8)
        y = 32 + self.base_footer - 14
        for text in lines:
            p.text(self.left, y, text, size=6.3, color=GRAY)
            y -= 8
        p.text(self.right, 34, f"{page}/{pages}", size=7, color=GRAY, align="right")


# ------------------------------------------------------------------ carta


class Letter(Layout):
    """Carta de un tercero: membrete, destinatario, asunto, cuerpo y firma."""

    name = LayoutName.LETTER
    note_size = 10.0
    note_leading = 14.0

    def first_header(self, p: Painter, doc: PrintedDocument) -> float:
        y = PAGE_HEIGHT - 55
        p.text(self.left, y, doc.issuer.name, font=BOLD, size=12)
        head = wrap(doc.issuer.address, 300, size=8.5) + contact_lines(doc)
        y = p.lines(self.left, y - 14, head, leading=10.5, size=8.5, color=GRAY)
        y -= 18
        p.text(
            self.right, y, f"{doc.issuer_town}, {date_long(doc.issue_date)}", size=10, align="right"
        )
        y -= 28
        recipient = [doc.customer.name, *wrap(doc.customer.address, 260, size=10)]
        y = p.lines(self.left + 250, y, recipient, leading=13, size=10)
        y -= 20
        subject = wrap(
            f"Asunto: {doc.title.lower()}. Ref.: {doc.number}", self.width, font=BOLD, size=10
        )
        y = p.lines(self.left, y, subject, leading=13, font=BOLD, size=10)
        y -= 11
        p.text(self.left, y, "Estimado proveedor:", size=10)
        return y - 10

    def notes(self, doc: PrintedDocument) -> list[str]:
        closing = [
            "Atentamente,",
            doc.signatory or "",
            f"Administrador de fincas · {doc.issuer.name}",
        ]
        return [*doc.paragraphs, *[line for line in closing if line]]

    def columns(self, doc: PrintedDocument) -> list[Column]:
        del doc
        return []

    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float:
        del p, columns
        return y

    def cells(
        self, doc: PrintedDocument, line: PrintedLine, columns: list[Column]
    ) -> dict[str, list[str]]:
        del doc, line, columns
        return {"description": [""]}

    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None:
        del p, y, columns, cells, index, height

    def totals_height(self, doc: PrintedDocument) -> float:
        del doc
        return 0.0

    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float:
        del p, doc
        return y

    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None:
        del page, pages
        p.hline(self.left, self.right, 50, color=GRAY, width=0.3)
        p.text(self.left, 40, f"{doc.issuer.name} · {doc.issuer.address}", size=6.5, color=GRAY)


LAYOUTS: dict[LayoutName, Layout] = {
    LayoutName.CLASSIC_TABLE: ClassicTable(),
    LayoutName.WORD_EXPORT: WordExport(),
    LayoutName.GENERIC_SOFTWARE: GenericSoftware(),
    LayoutName.PLAIN_TEXT: PlainText(),
    LayoutName.LOGO_LONG_FOOTER: LogoLongFooter(),
    LayoutName.LETTER: Letter(),
}
