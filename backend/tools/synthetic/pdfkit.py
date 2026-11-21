"""Motor de paginación común a las maquetaciones (ReportLab, modo ``invariant``).

Las fuentes son las Vera que trae ReportLab, incrustadas en cada PDF, para que
ni la lectura ni la rasterización dependan de las fuentes del sistema. El modo
``invariant`` fija la fecha y el identificador del PDF: la misma entrada da los
mismos bytes.

El flujo es siempre el mismo: cabecera, filas de líneas, totales y notas, con
salto de página cuando no caben. Una fila no se parte entre páginas, salvo en
los documentos con la imperfección «línea partida»: ahí la primera fila que no
cabe deja el principio del concepto (con sus importes) en una página y el resto
del concepto en la siguiente.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from synthetic.model import TrapTechnique
from synthetic.printed import PrintedDocument, PrintedLine

PAGE_WIDTH, PAGE_HEIGHT = A4
REGULAR = "Vera"
BOLD = "Vera-Bold"
ITALIC = "Vera-Italic"
_FONT_FILES = {REGULAR: "Vera.ttf", BOLD: "VeraBd.ttf", ITALIC: "VeraIt.ttf"}

PDF_AUTHOR = "Kapataz - generador de datos sintéticos (ADR-020)"
PDF_SUBJECT = "Documento sintético de pruebas: no corresponde a ninguna persona ni empresa real."
PDF_KEYWORDS = "sintético, demostración, Kapataz"

type RGB = tuple[float, float, float]
BLACK: RGB = (0.0, 0.0, 0.0)
WHITE: RGB = (1.0, 1.0, 1.0)
GRAY: RGB = (0.45, 0.45, 0.45)
LIGHT: RGB = (0.92, 0.92, 0.92)


def register_fonts() -> None:
    """Registra las Vera una vez por proceso; sin compresión ASCII85 en los flujos."""
    rl_config.useA85 = 0
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in _FONT_FILES.items():
        if name not in registered:
            pdfmetrics.registerFont(TTFont(name, filename))


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    title: str
    width: float
    align: str = "left"


@dataclass(slots=True)
class RenderInfo:
    """Páginas del PDF y líneas partidas: (índice de la línea, página donde empieza)."""

    pages: int = 0
    split_lines: list[tuple[int, int]] = field(default_factory=list)


class Painter:
    """Ayudas de dibujo sobre el lienzo de ReportLab."""

    def __init__(self, canvas: Canvas) -> None:
        self.c = canvas

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        font: str = REGULAR,
        size: float = 9,
        color: RGB = BLACK,
        align: str = "left",
    ) -> None:
        self.c.setFont(font, size)
        self.c.setFillColorRGB(*color)
        if align == "right":
            self.c.drawRightString(x, y, value)
        elif align == "center":
            self.c.drawCentredString(x, y, value)
        else:
            self.c.drawString(x, y, value)
        self.c.setFillColorRGB(*BLACK)

    def lines(
        self,
        x: float,
        y: float,
        values: list[str],
        *,
        leading: float,
        font: str = REGULAR,
        size: float = 9,
        color: RGB = BLACK,
        align: str = "left",
    ) -> float:
        """Dibuja una línea debajo de otra y devuelve la ``y`` siguiente."""
        for value in values:
            self.text(x, y, value, font=font, size=size, color=color, align=align)
            y -= leading
        return y

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: RGB | None = None,
        stroke: RGB | None = BLACK,
        line_width: float = 0.5,
    ) -> None:
        self.c.setLineWidth(line_width)
        if fill is not None:
            self.c.setFillColorRGB(*fill)
        if stroke is not None:
            self.c.setStrokeColorRGB(*stroke)
        self.c.rect(x, y, width, height, stroke=int(stroke is not None), fill=int(fill is not None))
        self.c.setFillColorRGB(*BLACK)
        self.c.setStrokeColorRGB(*BLACK)

    def hline(
        self, x1: float, x2: float, y: float, *, color: RGB = BLACK, width: float = 0.5
    ) -> None:
        self.c.setLineWidth(width)
        self.c.setStrokeColorRGB(*color)
        self.c.line(x1, y, x2, y)
        self.c.setStrokeColorRGB(*BLACK)


def wrap(value: str, width: float, *, font: str = REGULAR, size: float = 9) -> list[str]:
    return list(simpleSplit(value, font, size, width)) or [""]


class Layout(ABC):
    """Una maquetación: cabeceras, filas, totales, notas y pie."""

    left = 45.0
    right = PAGE_WIDTH - 45.0
    row_size = 8.5
    row_leading = 10.5
    row_padding = 4.0
    note_size = 8.5
    note_leading = 11.0
    wrap_key = "description"

    @property
    def width(self) -> float:
        return self.right - self.left

    base_footer = 40.0
    trap_size = 6.5
    trap_leading = 8.5
    # En un escaneado, el aviso va algo mayor para que el OCR lo pueda leer.
    scanned_trap_size = 8.0
    scanned_trap_leading = 10.0

    def footer_height(self, doc: PrintedDocument) -> float:
        """Alto reservado al pie en cada página; la trampa de pie visible lo amplía."""
        _, leading = self.trap_type(doc)
        return self.base_footer + len(self.trap_footer_lines(doc)) * leading

    def trap_type(self, doc: PrintedDocument) -> tuple[float, float]:
        """Cuerpo e interlineado del aviso inyectado en el pie."""
        if doc.spec.scanned:
            return self.scanned_trap_size, self.scanned_trap_leading
        return self.trap_size, self.trap_leading

    def trap_footer_lines(self, doc: PrintedDocument) -> list[str]:
        trap = doc.trap
        if trap is None or trap.technique is not TrapTechnique.VISIBLE_FOOTER:
            return []
        size, _ = self.trap_type(doc)
        return wrap(trap.injected_text, self.width, size=size)

    def bottom(self, doc: PrintedDocument) -> float:
        return 30.0 + self.footer_height(doc)

    @abstractmethod
    def first_header(self, p: Painter, doc: PrintedDocument) -> float: ...

    def continuation_header(self, p: Painter, doc: PrintedDocument, page: int) -> float:
        y = PAGE_HEIGHT - 50
        p.text(self.left, y, f"{doc.title.capitalize()} {doc.number} (continuación)", size=8)
        p.text(self.right, y, f"Página {page}", size=8, align="right")
        return y - 22

    @abstractmethod
    def columns(self, doc: PrintedDocument) -> list[Column]: ...

    @abstractmethod
    def table_header(self, p: Painter, y: float, columns: list[Column]) -> float: ...

    @abstractmethod
    def cells(
        self, doc: PrintedDocument, line: PrintedLine, columns: list[Column]
    ) -> dict[str, list[str]]: ...

    @abstractmethod
    def draw_row(
        self,
        p: Painter,
        y: float,
        columns: list[Column],
        cells: dict[str, list[str]],
        index: int,
        height: float,
    ) -> None: ...

    @abstractmethod
    def totals_height(self, doc: PrintedDocument) -> float: ...

    @abstractmethod
    def draw_totals(self, p: Painter, y: float, doc: PrintedDocument) -> float: ...

    @abstractmethod
    def footer(self, p: Painter, doc: PrintedDocument, page: int, pages: int) -> None: ...

    def row_height(self, lines: int) -> float:
        return lines * self.row_leading + self.row_padding

    def notes(self, doc: PrintedDocument) -> list[str]:
        return list(doc.notes)

    def draw_trap_footer(self, p: Painter, doc: PrintedDocument) -> None:
        """El aviso inyectado, en gris y pequeño, justo encima del pie de la última página."""
        lines = self.trap_footer_lines(doc)
        size, leading = self.trap_type(doc)
        y = 30.0 + self.base_footer + (len(lines) - 1) * leading + 2
        p.lines(self.left, y, lines, leading=leading, size=size, color=GRAY)


def render_pdf(
    doc: PrintedDocument, layout: Layout, *, split_line: bool
) -> tuple[bytes, RenderInfo]:
    """Dos pasadas: la primera cuenta las páginas para el «Página n de N» de la segunda."""
    register_fonts()
    _, first = _paint(doc, layout, split_line=split_line, pages=0)
    data, info = _paint(doc, layout, split_line=split_line, pages=first.pages)
    if info.pages != first.pages:
        raise AssertionError("La paginación cambió entre pasadas.")
    if split_line and not info.split_lines:
        msg = f"{doc.spec.doc_id}: no hubo ninguna línea que partir entre páginas."
        raise ValueError(msg)
    return data, info


def new_canvas(
    buffer: BytesIO,
    title: str,
    *,
    subject: str = PDF_SUBJECT,
    keywords: str = PDF_KEYWORDS,
) -> Canvas:
    """Lienzo con los metadatos de un documento sintético; ``subject`` cambia en una trampa."""
    canvas = Canvas(buffer, pagesize=A4, invariant=1, pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor(PDF_AUTHOR)
    canvas.setSubject(subject)
    canvas.setCreator(PDF_AUTHOR)
    canvas.setKeywords(keywords)
    return canvas


def pdf_subject(doc: PrintedDocument) -> str:
    """El aviso de documento sintético o, en la trampa de metadatos, la instrucción inyectada."""
    trap = doc.trap
    if trap is not None and trap.technique is TrapTechnique.METADATA:
        return trap.injected_text
    return PDF_SUBJECT


class _Flow:
    def __init__(self, doc: PrintedDocument, layout: Layout, canvas: Canvas, pages: int) -> None:
        self.doc = doc
        self.layout = layout
        self.canvas = canvas
        self.p = Painter(canvas)
        self.pages = pages
        self.page = 1
        self.normal_bottom = layout.bottom(doc)
        self.bottom = self.normal_bottom
        self.info = RenderInfo()

    def new_page(self, columns: list[Column] | None) -> float:
        self.finish_page()
        self.canvas.showPage()
        self.page += 1
        self.bottom = self.normal_bottom
        y = self.layout.continuation_header(self.p, self.doc, self.page)
        if columns is not None:
            y = self.layout.table_header(self.p, y, columns)
        return y

    def finish_page(self) -> None:
        self.layout.footer(self.p, self.doc, self.page, self.pages)
        if self.layout.trap_footer_lines(self.doc) and self.page == self.pages:
            self.layout.draw_trap_footer(self.p, self.doc)


def _paint(
    doc: PrintedDocument, layout: Layout, *, split_line: bool, pages: int
) -> tuple[bytes, RenderInfo]:
    buffer = BytesIO()
    canvas = new_canvas(buffer, f"Documento {doc.spec.doc_id}", subject=pdf_subject(doc))
    flow = _Flow(doc, layout, canvas, pages)
    y = layout.first_header(flow.p, doc)
    columns = layout.columns(doc)
    if doc.lines:
        y = layout.table_header(flow.p, y, columns)
    rows = [layout.cells(doc, line, columns) for line in doc.lines]
    if split_line:
        flow.bottom = max(flow.bottom, _forced_bottom(layout, y, rows))
    for index, cells in enumerate(rows):
        count = max(len(value) for value in cells.values())
        height = layout.row_height(count)
        if y - height < flow.bottom:
            if split_line and not flow.info.split_lines:
                done = _split_row(flow, y, columns, cells, index)
                if done is not None:
                    y = done
                    continue
            y = flow.new_page(columns)
        layout.draw_row(flow.p, y, columns, cells, index, height)
        y -= height
    if doc.totals is not None:
        if y - layout.totals_height(doc) < flow.bottom:
            y = flow.new_page(None)
        y = layout.draw_totals(flow.p, y, doc)
    y = _notes(flow, y)
    _hidden_text(flow, y)
    flow.finish_page()
    canvas.save()
    flow.info.pages = flow.page
    return buffer.getvalue(), flow.info


def _forced_bottom(layout: Layout, y: float, rows: list[dict[str, list[str]]]) -> float:
    """Final de la primera página que deja partida una fila de la segunda mitad.

    Si la tabla cabe entera en la primera página, la página se corta antes, como
    haría un salto de página manual, para que la imperfección exista siempre.
    """
    top = y
    for index, cells in enumerate(rows):
        wrapped = len(cells[layout.wrap_key])
        others = max((len(v) for k, v in cells.items() if k != layout.wrap_key), default=1)
        if index >= len(rows) // 2 and wrapped >= max(2, others + 1):
            keep = 1 if wrapped == 2 else 2  # noqa: PLR2004 - una o dos líneas en esta página
            return top - layout.row_padding - (keep + 0.5) * layout.row_leading
        top -= layout.row_height(max(len(value) for value in cells.values()))
    msg = "Ninguna fila de la segunda mitad tiene un concepto que se pueda partir."
    raise ValueError(msg)


def _split_row(
    flow: _Flow,
    y: float,
    columns: list[Column],
    cells: dict[str, list[str]],
    index: int,
) -> float | None:
    """Parte la fila: el principio del concepto y los importes aquí, el resto en la siguiente."""
    layout = flow.layout
    wrapped = cells[layout.wrap_key]
    others = max((len(v) for k, v in cells.items() if k != layout.wrap_key), default=1)
    fit = int((y - flow.bottom - layout.row_padding) // layout.row_leading)
    if fit < max(1, others) or fit >= len(wrapped):
        return None
    head = {
        key: (value if key != layout.wrap_key else wrapped[:fit]) for key, value in cells.items()
    }
    layout.draw_row(flow.p, y, columns, head, index, layout.row_height(fit))
    flow.info.split_lines.append((index, flow.page))
    y = flow.new_page(columns)
    tail = {key: (wrapped[fit:] if key == layout.wrap_key else []) for key in cells}
    height = layout.row_height(len(wrapped) - fit)
    layout.draw_row(flow.p, y, columns, tail, index, height)
    return y - height


def _notes(flow: _Flow, y: float) -> float:
    layout = flow.layout
    y -= 8
    for note in layout.notes(flow.doc):
        for text in wrap(note, layout.width, size=layout.note_size):
            if y - layout.note_leading < flow.bottom:
                y = flow.new_page(None)
            flow.p.text(layout.left, y, text, size=layout.note_size)
            y -= layout.note_leading
        y -= 3
    return y


def _hidden_text(flow: _Flow, y: float) -> None:
    """Trampa de texto oculto: blanco y de un punto, invisible al ojo pero no al lector."""
    trap = flow.doc.trap
    if trap is None or trap.technique is not TrapTechnique.HIDDEN_TEXT:
        return
    lines = wrap(trap.injected_text, flow.layout.width, size=1)
    flow.p.lines(flow.layout.left, max(y - 4, flow.bottom), lines, leading=1.2, size=1, color=WHITE)
