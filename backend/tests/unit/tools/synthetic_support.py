"""Ayudas de las pruebas del generador de datos sintéticos (ADR-020)."""

from __future__ import annotations

import json
import re
import zlib
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path

import pypdfium2 as pdfium

from synthetic.fingerprint import sha256
from synthetic.output import MANIFEST, SAMPLES_DIR, dataset_digest, to_json

REPO_ROOT = Path(__file__).resolve().parents[4]
SAMPLES = REPO_ROOT / "samples"
EVALS = REPO_ROOT / "evals" / "extraction"
_SPACES = re.compile(r"\s+")
CENT = Decimal("0.01")


def normalize(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def pdf_pages_text(path: Path) -> list[str]:
    """Texto de cada página según PDFium, con los espacios normalizados."""
    document = pdfium.PdfDocument(path.read_bytes())
    pages = []
    try:
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            pages.append(normalize(textpage.get_text_range()))
            textpage.close()
            page.close()
    finally:
        document.close()
    return pages


def pdf_metadata(path: Path) -> dict[str, str]:
    """El diccionario /Info del PDF según PDFium."""
    document = pdfium.PdfDocument(path.read_bytes())
    try:
        return {str(key): str(value) for key, value in document.get_metadata_dict().items()}
    finally:
        document.close()


def pdf_title(path: Path) -> str:
    return pdf_metadata(path).get("Title", "")


_DELIMITER = rb"\s()<>\[\]{}/%"
_STREAM = re.compile(rb">>[ \t\r\n]*stream(?:\r\n|\n)")
_LENGTH = re.compile(
    rb"/Length[ \t\r\n]+(\d+)(?![ \t\r\n]+\d+[ \t\r\n]+R)(?=[" + _DELIMITER + rb"])"
)
_NAME = re.compile(rb"/[^" + _DELIMITER + rb"]*")
_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_FILTER = re.compile(rb"/Filter[ \t\r\n]*(\[[^\]]*\]|/[^" + _DELIMITER + rb"]+)")
_ENCRYPT = re.compile(rb"/Encrypt(?=[" + _DELIMITER + rb"])")
# Mucho más de lo que descomprime cualquier flujo generado (32 KB): corta las bombas zlib.
MAX_INFLATED = 4 * 1024 * 1024


def decode_names(data: bytes) -> bytes:
    """Resuelve los escapes ``#xx`` de los nombres: ``/Open#41ction`` es ``/OpenAction``."""

    def unescape(name: re.Match[bytes]) -> bytes:
        return _HEX_ESCAPE.sub(lambda code: bytes([int(code.group(1), 16)]), name.group(0))

    return _NAME.sub(unescape, data)


def inflate(data: bytes) -> bytes:
    """Flate con límite de tamaño, entero y sin bytes detrás."""
    inflater = zlib.decompressobj()
    out = inflater.decompress(data, MAX_INFLATED + 1)
    if len(out) > MAX_INFLATED or not inflater.eof or inflater.unused_data:
        msg = "Flujo Flate demasiado grande, incompleto o con bytes detrás."
        raise AssertionError(msg)
    return out


def pdf_syntax(pdf: bytes) -> bytes:
    """Todo lo que lleva el PDF, con los nombres decodificados: lo de fuera de los flujos
    y cada flujo, descomprimido si es Flate y tal cual si es DCT o no tiene filtro.

    No se salta ningún flujo, tampoco las fuentes ni las imágenes: un ``/Length1`` o un
    ``/Subtype /Image`` se pueden poner en cualquier flujo para esconderlo. Un filtro
    distinto de Flate y DCT, un ``/Length`` indirecto o un ``/Encrypt`` hacen fallar.
    """
    parts: list[bytes] = []
    position = 0
    while (match := _STREAM.search(pdf, position)) is not None:
        start = match.end()
        header = decode_names(pdf[pdf.rfind(b" obj", position, match.start()) : match.start()])
        lengths = _LENGTH.findall(header)
        if len(lengths) != 1:
            msg = "Flujo de PDF sin un /Length directo."
            raise AssertionError(msg)
        end = start + int(lengths[0])
        parts.append(pdf[position:start])
        data = pdf[start:end]
        filters = [_NAME.findall(found) for found in _FILTER.findall(header)]
        if filters == [[b"/FlateDecode"]]:
            parts.append(inflate(data))
        elif filters in ([], [[b"/DCTDecode"]]):
            parts.append(data)
        else:
            msg = f"Filtro de PDF no admitido: {filters}"
            raise AssertionError(msg)
        position = end
    parts.append(pdf[position:])
    syntax = decode_names(b"".join(parts))
    if _ENCRYPT.search(syntax):
        msg = "PDF cifrado."
        raise AssertionError(msg)
    return syntax


# Nombres de PDF que ejecutan algo, abren algo o llevan algo dentro (S3-10), y los de
# una actualización incremental o un cifrado (S3-R-01). Se buscan en ``pdf_syntax``,
# con los escapes ``#xx`` ya resueltos: ``/Open#41ction`` cuenta como ``/OpenAction``.
ACTIVE = re.compile(
    rb"/(JavaScript|JS|OpenAction|AA|Launch|EmbeddedFiles|Annots|AcroForm|URI|XFA"
    rb"|RichMedia|GoToR|GoToE|SubmitForm|ImportData|ObjStm|XRefStm|XRef|Prev|Encrypt)"
    rb"(?=[\s()<>\[\]{}/%]|$)",
)


def single_revision_problems(data: bytes) -> list[str]:
    """Un PDF sin actualizaciones incrementales: un ``startxref`` y un ``%%EOF``, al final."""
    problems = [
        f"{count} «{keyword.decode()}»"
        for keyword in (b"startxref", b"%%EOF", b"trailer")
        if (count := data.count(keyword)) != 1
    ]
    if not data.endswith(b"%%EOF\n"):
        problems.append("bytes después del %%EOF")
    return problems


# Teléfonos con forma española: nueve cifras, con o sin +34 o 0034 delante, juntas o
# separadas por un espacio, un punto o un guion. Una ristra de más cifras no cuenta.
_PHONE_LIKE = re.compile(r"(?<![\w+])(?:(?:\+|00)34[ .-]?)?(\d(?:[ .-]?\d){8})(?!\w)")
_PHONE_SEPARATORS = str.maketrans("", "", " .-")
# El único segmento del Plan nacional de numeración que se admite (S3-R-02): N=4,
# pendiente de atribución (RD 2296/2004, apartado 4.4). Con 0 o 1 delante, el número
# empieza por un número corto o un prefijo (0XY y 1XYA, apartado 10.1: 016, 061, 062,
# 091, 092, 112…); con 2, por un código interno de operador (22XXX, 242), y del 5 al
# 9 puede ser de un abonado real.
SAFE_PHONE_SEGMENT = "4"


def phone_numbers(text: str) -> list[str]:
    """Las nueve cifras nacionales de cada cosa con forma de teléfono que hay en ``text``."""
    return [match.group(1).translate(_PHONE_SEPARATORS) for match in _PHONE_LIKE.finditer(text)]


def assert_unreachable_phones(text: str, where: object) -> None:
    """Ningún teléfono del texto se puede marcar hacia una persona ni hacia un servicio."""
    for number in phone_numbers(text):
        assert number.startswith(SAFE_PHONE_SEGMENT), (where, number)


def dec(value: str | None) -> Decimal:
    """Cadena decimal del JSON a Decimal; un importe ausente cuenta como cero."""
    return Decimal(value) if value is not None else Decimal(0)


def round_cents(value: Decimal) -> Decimal:
    """Un solo redondeo a céntimos, mitad hacia arriba (RN-03), con precisión de sobra."""
    with localcontext() as context:
        context.prec = 50
        return value.quantize(CENT, rounding=ROUND_HALF_UP)


def percent(base: Decimal, rate: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return round_cents(base * rate / 100)


def replace_on_disk(root: Path, path: str, data: bytes, *, content: str | None = None) -> None:
    """Sustituye un fichero y deja el manifiesto coherente con él, como haría un atacante."""
    (root / path).write_bytes(data)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == path:
            entry["sha256"] = sha256(data)
            entry["bytes"] = len(data)
            if content is not None:
                entry["content_sha256"] = content
    manifest["dataset_sha256"] = dataset_digest(manifest["files"])
    manifest["summary"]["samples_bytes"] = sum(
        entry["bytes"] for entry in manifest["files"] if entry["path"].startswith(f"{SAMPLES_DIR}/")
    )
    (root / MANIFEST).write_bytes(to_json(manifest))
