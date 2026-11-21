"""Huellas de los ficheros generados y validación estricta de la estructura de un PDF.

``sha256`` es la huella de los bytes del fichero. ``content_fingerprint`` es la
del PDF entero, de la cabecera al ``%%EOF``, con solo lo que cambia de una
plataforma a otra puesto en forma canónica:

- los flujos Flate, descomprimidos: la zlib de la máquina (la de CPython en
  Windows, la del sistema en Linux, zlib-ng) puede comprimir los mismos datos con
  otros bytes;
- los flujos DCT (las imágenes JPEG de los escaneados), sustituidos por un
  marcador: libjpeg-turbo puede codificar la misma imagen con otros bytes. La
  imagen se compara aparte, píxel a píxel (``scan.scan_differences``);
- los ``/Length`` de los flujos, los desplazamientos de las entradas en uso de la
  tabla de referencias y el valor de ``startxref``, que dependen de lo anterior.
  Antes de normalizarlos se comprueba que son los correctos;
- el nombre del XObject de cada imagen (``/FormXob.<md5>``): ReportLab lo calcula
  con el MD5 de los píxeles decodificados, que dependen del decodificador JPEG.

Todo lo demás entra tal cual: los diccionarios, la tabla de referencias sin sus
desplazamientos, el ``trailer`` con su ``/ID`` (que ReportLab, en modo
``invariant``, calcula solo con los metadatos), los flujos descomprimidos y lo
que haya entre objetos. Cada trozo entra con su tipo y su longitud, así que
tampoco se puede mover el límite entre dos trozos sin cambiar la huella.

La estructura tiene que ser la de un PDF de ReportLab sin actualizaciones; si
no, se lanza ``PdfStructureError``:

- una sola tabla de referencias clásica, un solo ``trailer``, un solo
  ``startxref`` y un solo ``%%EOF``, y nada detrás del ``%%EOF``;
- ni ``/Prev``, ni ``/XRefStm``, ni ``/XRef``, ni ``/ObjStm``, ni ``/Encrypt``,
  tampoco escritos con escapes ``#xx``;
- flujos sin filtro, Flate o DCT, con un ``/Length`` directo que acaba en
  ``endstream``, sin ``/F`` ni ``/DecodeParms``; los Flate, completos, sin bytes
  detrás y de tamaño acotado (bombas zlib);
- los DCT, un JPEG de línea base en escala de grises con los segmentos que
  escribe libjpeg desde Pillow y en su orden: SOI; un APP0 que es exactamente el
  JFIF 1.01 de libjpeg (sin unidades, relación de aspecto 1:1 y sin miniatura);
  una tabla de cuantización; una cabecera SOF0 de 8 bits y un componente, con las
  mismas dimensiones que ``/Width`` y
  ``/Height`` del diccionario del flujo y sin pasar de ``MAX_IMAGE_SIDE``; las
  tablas de Huffman DC y AC de ese componente; un intervalo de reinicio
  opcional; una cabecera SOS de ese componente con la selección espectral
  completa; los datos de la imagen, donde un ``FF`` solo va seguido de ``00`` o,
  si hay intervalo de reinicio, de ``D0``-``D7`` en orden; y el EOI como últimos
  dos bytes. Ni COM, ni APP1-APP15, ni segmentos repetidos ni bytes tras el EOI.
  El contenido de las tablas no se compara byte a byte: queda ligado por los
  píxeles, que se comparan aparte;
- cada entrada en uso de la tabla apunta a la cabecera de su objeto, fuera de
  los flujos, y ``startxref`` apunta a la tabla.
"""

import hashlib
import re
import zlib
from dataclasses import dataclass

# Un flujo Flate de los PDF generados descomprime a menos de 32 KB (la fuente más
# grande), y todos los de un documento, a unos 120 KB. Los límites dejan margen de
# sobra y cortan una bomba zlib antes de que ocupe memoria.
MAX_STREAM_BYTES = 4 * 1024 * 1024
MAX_DECODED_BYTES = 32 * 1024 * 1024

_DELIMITER = rb"\s()<>\[\]{}/%"
_NAME = re.compile(rb"/[^" + _DELIMITER + rb"]*")
_HEX_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_STREAM = re.compile(rb">>[ \t\r\n]*stream(?:\r\n|\n)")
_ENDSTREAM = re.compile(rb"(?:\r\n|\n)?endstream")
_OBJECT = re.compile(rb"(?m)^(\d+) (\d+) obj(?=[" + _DELIMITER + rb"])")
_LENGTH = re.compile(
    rb"/Length[ \t\r\n]+(\d+)(?![ \t\r\n]+\d+[ \t\r\n]+R)(?=[" + _DELIMITER + rb"])",
)
_FILTER = re.compile(rb"/Filter[ \t\r\n]*(\[[^\]]*\]|/[^" + _DELIMITER + rb"]+)")
_XREF_KEYWORD = re.compile(rb"(?m)^xref(?=[\r\n])")
_XREF = re.compile(
    rb"xref\r?\n0 (?P<count>\d+)\r?\n(?P<entries>(?:\d{10} \d{5} [nf](?: \r?\n|\r\n))*)"
    rb"trailer[ \t\r\n]*<<.*?>>[ \t\r\n]*startxref\r?\n(?P<startxref>\d+)\r?\n%%EOF\r?\n\Z",
    re.DOTALL,
)
_XREF_ENTRY = re.compile(rb"(\d{10}) (\d{5}) ([nf])")
_IMAGE_NAME = re.compile(rb"/FormXob\.[0-9a-f]{32}")
_FORBIDDEN_NAMES = frozenset({b"/Prev", b"/XRefStm", b"/XRef", b"/ObjStm", b"/Encrypt"})
_FORBIDDEN_STREAM_KEYS = frozenset({b"/F", b"/FFilter", b"/FDecodeParms", b"/DecodeParms"})
_SINGLE_KEYWORDS = (b"trailer", b"startxref", b"%%EOF")
_FLATE = b"/FlateDecode"
_DCT = b"/DCTDecode"
# Los escaneados miden 1241 x 1754 píxeles (A4 a 150 ppp). El límite corta una
# imagen enorme antes de que PDFium la decodifique en memoria.
MAX_IMAGE_SIDE = 4096

# Un JPEG como lo escribe libjpeg desde Pillow para una imagen en escala de grises
# (``scan.py``), comprobado con el de los escaneados y con el recodificado a otra
# calidad: los segmentos van en este orden y ninguno puede llevar texto.
_JPEG_SOI, _JPEG_EOI, _JPEG_FF = b"\xff\xd8", b"\xff\xd9", b"\xff"
_JPEG_MARK = 0xFF
_APP0, _DQT, _SOF0, _DHT, _DRI, _SOS = 0xE0, 0xDB, 0xC0, 0xC4, 0xDD, 0xDA
_RST0, _RST_COUNT = 0xD0, 8
# APP0 entero: longitud 16, «JFIF\0», versión 1.01, sin unidades, densidad 1 x 1 y
# miniatura de 0 x 0. Es lo que escribe Pillow cuando no se le da resolución.
_JFIF_APP0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
# Una tabla de cuantización de 8 bits (la 0): Pq/Tq y 64 valores.
_DQT_LENGTH = 2 + 1 + 64
_DQT_TABLE = 0x00
# Las dos tablas de Huffman del componente: DC 0 (0x00) y AC 0 (0x10).
_DHT_TABLES = (0x00, 0x10)
_DHT_COUNTS = 16
_DRI_LENGTH = 4
# SOF0: precisión 8, alto, ancho, un componente (id, muestreo 1x1, tabla 0).
_SOF0_LENGTH = 2 + 6 + 3
_SOF0_PRECISION = 8
_SOF0_SAMPLING = 0x11
# SOS: un componente con las tablas 0/0, Ss 0, Se 63 y sin aproximación sucesiva.
_SOS_LENGTH = 2 + 1 + 2 + 3
_SOS_TABLES = 0x00
_SOS_SPECTRAL = b"\x00\x3f\x00"
_JPEG_HEADER_ORDER = (_APP0, _DQT, _SOF0, _DHT, _DHT)
_DIMENSION = re.compile(
    rb"/(Width|Height)[ \t\r\n]+(\d+)(?![ \t\r\n]+\d+[ \t\r\n]+R)(?=[" + _DELIMITER + rb"])",
)


class PdfStructureError(ValueError):
    """El PDF no tiene la estructura de uno generado: actualizaciones, cifrado, filtros…"""


@dataclass(frozen=True, slots=True)
class _Stream:
    header_start: int
    header: bytes
    data_start: int
    data: bytes

    @property
    def data_end(self) -> int:
        return self.data_start + len(self.data)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unescape(name: re.Match[bytes]) -> bytes:
    return _HEX_ESCAPE.sub(lambda code: bytes([int(code.group(1), 16)]), name.group(0))


def decode_names(syntax: bytes) -> bytes:
    """Los nombres con sus escapes ``#xx`` resueltos: ``/Open#41ction`` es ``/OpenAction``."""
    return _NAME.sub(_unescape, syntax)


def inflate(data: bytes, *, limit: int = MAX_STREAM_BYTES) -> bytes:
    """Descomprime un flujo Flate entero, sin bytes de más y sin pasar de ``limit``."""
    inflater = zlib.decompressobj()
    try:
        out = inflater.decompress(data, limit + 1)
    except zlib.error as error:
        msg = f"Flujo Flate corrupto: {error}"
        raise PdfStructureError(msg) from error
    if len(out) > limit:
        msg = f"Flujo Flate de más de {limit} bytes descomprimido."
        raise PdfStructureError(msg)
    if not inflater.eof or inflater.unconsumed_tail:
        raise PdfStructureError("Flujo Flate incompleto.")
    if inflater.unused_data:
        raise PdfStructureError("Bytes después del final de un flujo Flate.")
    return out


def stream_filters(header: bytes) -> list[bytes]:
    """Los filtros del diccionario de un flujo, con los nombres decodificados."""
    found = _FILTER.findall(decode_names(header))
    if len(found) > 1:
        raise PdfStructureError("Flujo con más de un /Filter.")
    return _NAME.findall(found[0]) if found else []


@dataclass(frozen=True, slots=True)
class _JpegSegment:
    marker: int
    raw: bytes

    @property
    def payload(self) -> bytes:
        return self.raw[4:]


def _image_size(header: bytes) -> tuple[int, int]:
    """``/Width`` y ``/Height`` directos del diccionario de un flujo de imagen."""
    found: dict[bytes, list[int]] = {b"Width": [], b"Height": []}
    for key, value in _DIMENSION.findall(decode_names(header)):
        found[key].append(int(value))
    if len(found[b"Width"]) != 1 or len(found[b"Height"]) != 1:
        raise PdfStructureError("Imagen sin un /Width y un /Height directos.")
    return found[b"Width"][0], found[b"Height"][0]


def _jpeg_header(data: bytes) -> tuple[list[_JpegSegment], int]:
    """Los segmentos de SOI a SOS, en el orden de libjpeg, y dónde empiezan los datos."""
    if not data.startswith(_JPEG_SOI):
        raise PdfStructureError("Flujo DCT que no es un JPEG.")
    segments: list[_JpegSegment] = []
    position = len(_JPEG_SOI)
    while True:
        if position + 4 > len(data) or data[position] != _JPEG_MARK:
            raise PdfStructureError("JPEG con los segmentos mal formados.")
        marker = data[position + 1]
        index = len(segments)
        if index < len(_JPEG_HEADER_ORDER):
            allowed = {_JPEG_HEADER_ORDER[index]}
        else:
            allowed = {_DRI, _SOS} if index == len(_JPEG_HEADER_ORDER) else {_SOS}
        if marker not in allowed:
            msg = f"JPEG con un segmento no admitido o fuera de orden (0xFF{marker:02X})."
            raise PdfStructureError(msg)
        end = position + 2 + int.from_bytes(data[position + 2 : position + 4], "big")
        if end > len(data) or end < position + 4:
            raise PdfStructureError("JPEG con un segmento de longitud imposible.")
        segments.append(_JpegSegment(marker, data[position:end]))
        position = end
        if marker == _SOS:
            return segments, position


def _check_tables(segments: list[_JpegSegment]) -> None:
    """APP0 JFIF exacto, una tabla de cuantización y las tablas DC 0 y AC 0."""
    app0, dqt, _sof, *dht = segments[: len(_JPEG_HEADER_ORDER)]
    if app0.raw != _JFIF_APP0:
        raise PdfStructureError("JPEG con un APP0 distinto del JFIF de libjpeg.")
    if len(dqt.raw) != 2 + _DQT_LENGTH or dqt.payload[0] != _DQT_TABLE:
        raise PdfStructureError("JPEG con una tabla de cuantización no admitida.")
    for table, segment in zip(_DHT_TABLES, dht, strict=True):
        payload = segment.payload
        symbols = sum(payload[1 : 1 + _DHT_COUNTS])
        if payload[:1] != bytes([table]) or len(payload) != 1 + _DHT_COUNTS + symbols:
            raise PdfStructureError("JPEG con una tabla de Huffman no admitida.")


def _check_frame(segments: list[_JpegSegment], size: tuple[int, int]) -> int:
    """SOF0 y SOS de un solo componente, con el tamaño del diccionario; devuelve el
    intervalo de reinicio (0 si no hay DRI)."""
    sof, sos = segments[2], segments[-1]
    payload = sof.payload
    height = int.from_bytes(payload[1:3], "big")
    width = int.from_bytes(payload[3:5], "big")
    if (
        len(sof.raw) != 2 + _SOF0_LENGTH
        or payload[0] != _SOF0_PRECISION
        or payload[5] != 1
        or payload[7:9] != bytes([_SOF0_SAMPLING, _DQT_TABLE])
    ):
        raise PdfStructureError("JPEG que no es de línea base, 8 bits y un componente.")
    if (width, height) != size:
        msg = f"JPEG de {width}x{height} en una imagen de {size[0]}x{size[1]}."
        raise PdfStructureError(msg)
    if not (0 < width <= MAX_IMAGE_SIDE and 0 < height <= MAX_IMAGE_SIDE):
        msg = f"Imagen de {width}x{height}: el máximo es {MAX_IMAGE_SIDE} de lado."
        raise PdfStructureError(msg)
    component = payload[6]
    if sos.raw[2:] != (
        _SOS_LENGTH.to_bytes(2, "big") + bytes([1, component, _SOS_TABLES]) + _SOS_SPECTRAL
    ):
        raise PdfStructureError("JPEG con una cabecera de barrido no admitida.")
    if len(segments) == len(_JPEG_HEADER_ORDER) + 1:
        return 0
    dri = segments[len(_JPEG_HEADER_ORDER)]
    interval = int.from_bytes(dri.payload, "big")
    if len(dri.raw) != 2 + _DRI_LENGTH or interval == 0:
        raise PdfStructureError("JPEG con un intervalo de reinicio no admitido.")
    return interval


def _check_scan(data: bytes, start: int, *, restarts: bool) -> None:
    """Datos de la imagen hasta un EOI que son los dos últimos bytes del flujo."""
    position, restart = start, 0
    while (mark := data.find(_JPEG_FF, position)) >= 0 and mark + 1 < len(data):
        follower = data[mark + 1]
        position = mark + 2
        if follower == 0:
            continue
        if restarts and follower == _RST0 + restart % _RST_COUNT:
            restart += 1
            continue
        if follower == _JPEG_EOI[1] and position == len(data):
            return
        msg = f"JPEG con un marcador 0xFF{follower:02X} en los datos de la imagen o tras ellos."
        raise PdfStructureError(msg)
    raise PdfStructureError("JPEG sin el final de la imagen.")


def _check_jpeg(data: bytes, header: bytes) -> None:
    """El JPEG que escribe libjpeg desde Pillow (ver el docstring del módulo)."""
    segments, scan = _jpeg_header(data)
    _check_tables(segments)
    interval = _check_frame(segments, _image_size(header))
    _check_scan(data, scan, restarts=interval > 0)


def _streams(pdf: bytes) -> list[_Stream]:
    """Los flujos en orden, delimitados por su ``/Length`` y seguidos de ``endstream``."""
    streams: list[_Stream] = []
    position = 0
    while (match := _STREAM.search(pdf, position)) is not None:
        header_start = pdf.rfind(b" obj", position, match.start())
        if header_start < 0:
            raise PdfStructureError("Flujo fuera de un objeto.")
        header = pdf[header_start : match.start() + 2]
        lengths = _LENGTH.findall(header)
        if len(lengths) != 1:
            raise PdfStructureError("Flujo sin un /Length directo.")
        data_start = match.end()
        stream = _Stream(
            header_start, header, data_start, pdf[data_start : data_start + int(lengths[0])]
        )
        if _ENDSTREAM.match(pdf, stream.data_end) is None:
            raise PdfStructureError("Flujo cuyo /Length no acaba en endstream.")
        streams.append(stream)
        position = stream.data_end
    return streams


def _decoded(stream: _Stream) -> tuple[bytes, bytes]:
    """El tipo y el contenido canónico de un flujo: tal cual, descomprimido o un marcador."""
    keys = set(_NAME.findall(decode_names(stream.header))) & _FORBIDDEN_STREAM_KEYS
    if keys:
        msg = f"Flujo con claves no admitidas: {b' '.join(sorted(keys)).decode('latin-1')}."
        raise PdfStructureError(msg)
    filters = stream_filters(stream.header)
    if not filters:
        return b"R", stream.data
    if filters == [_FLATE]:
        return b"D", inflate(stream.data)
    if filters == [_DCT]:
        _check_jpeg(stream.data, stream.header)
        return b"J", b""
    msg = f"Filtro no admitido: {b' '.join(filters).decode('latin-1')}."
    raise PdfStructureError(msg)


def _syntax_parts(pdf: bytes, streams: list[_Stream]) -> list[tuple[int, bytes]]:
    """Los trozos del PDF fuera de los flujos, con su desplazamiento."""
    parts: list[tuple[int, bytes]] = []
    position = 0
    for stream in streams:
        parts.append((position, pdf[position : stream.data_start]))
        position = stream.data_end
    parts.append((position, pdf[position:]))
    return parts


def _check_syntax(parts: list[tuple[int, bytes]]) -> int:
    """Rechaza nombres prohibidos y palabras clave repetidas; devuelve dónde está ``xref``."""
    syntax = b"\n".join(part for _, part in parts)
    if forbidden := set(_NAME.findall(decode_names(syntax))) & _FORBIDDEN_NAMES:
        msg = f"PDF con {b', '.join(sorted(forbidden)).decode('latin-1')}."
        raise PdfStructureError(msg)
    for keyword in _SINGLE_KEYWORDS:
        if (count := syntax.count(keyword)) != 1:
            msg = f"PDF con {count} «{keyword.decode()}»: se admite uno solo."
            raise PdfStructureError(msg)
    tables = [base + m.start() for base, part in parts for m in _XREF_KEYWORD.finditer(part)]
    if len(tables) != 1 or tables[0] < parts[-1][0]:
        msg = f"PDF con {len(tables)} tablas de referencias fuera de flujos: se admite una sola."
        raise PdfStructureError(msg)
    return tables[0]


def _objects(parts: list[tuple[int, bytes]]) -> dict[int, tuple[int, int]]:
    """Número de objeto → (desplazamiento, generación), de las cabeceras fuera de flujos."""
    objects: dict[int, tuple[int, int]] = {}
    for base, part in parts:
        for match in _OBJECT.finditer(part):
            number = int(match.group(1))
            if number in objects:
                msg = f"Objeto {number} definido dos veces."
                raise PdfStructureError(msg)
            objects[number] = (base + match.start(), int(match.group(2)))
    return objects


def _without_offset(entry: re.Match[bytes]) -> bytes:
    """Una entrada en uso sin su desplazamiento, ya comprobado; las libres, tal cual."""
    if entry.group(3) == b"n":
        return b"0000000000 " + entry.group(2) + b" n"
    return entry.group(0)


def _canonical_xref(pdf: bytes, table: int, objects: dict[int, tuple[int, int]]) -> bytes:
    """Comprueba la tabla, el trailer y ``startxref`` y los devuelve sin desplazamientos."""
    match = _XREF.match(pdf, table)
    if match is None:
        raise PdfStructureError("Tabla de referencias, trailer o %%EOF con forma no admitida.")
    if int(match.group("startxref")) != table:
        raise PdfStructureError("startxref no apunta a la tabla de referencias.")
    entries = _XREF_ENTRY.findall(match.group("entries"))
    if len(entries) != int(match.group("count")):
        raise PdfStructureError("La tabla de referencias no tiene las entradas que declara.")
    in_use = {
        number: (int(offset), int(generation))
        for number, (offset, generation, kind) in enumerate(entries)
        if kind == b"n"
    }
    if in_use != objects:
        raise PdfStructureError("La tabla de referencias no apunta a los objetos del PDF.")
    entries_start, entries_end = match.span("entries")
    return (
        pdf[table:entries_start]
        + _XREF_ENTRY.sub(_without_offset, pdf[entries_start:entries_end])
        + pdf[entries_end : match.start("startxref")]
        + b"0"
        + pdf[match.end("startxref") :]
    )


def content_fingerprint(pdf: bytes) -> str:
    """SHA-256 del PDF completo en forma canónica (ver el docstring del módulo).

    Lanza ``PdfStructureError`` si el PDF no tiene la estructura de uno generado.
    """
    streams = _streams(pdf)
    parts = _syntax_parts(pdf, streams)
    table = _check_syntax(parts)
    xref = _canonical_xref(pdf, table, _objects(parts))
    pieces: list[tuple[bytes, bytes]] = []
    decoded = 0
    for (base, part), stream in zip(parts, streams, strict=False):
        header = stream.header_start - base
        pieces.append((b"S", part[:header] + _LENGTH.sub(b"/Length", part[header:])))
        kind, data = _decoded(stream)
        decoded += len(data)
        if decoded > MAX_DECODED_BYTES:
            msg = f"PDF de más de {MAX_DECODED_BYTES} bytes descomprimido."
            raise PdfStructureError(msg)
        pieces.append((kind, data))
    base, tail = parts[-1]
    pieces.append((b"S", tail[: table - base] + xref))
    digest = hashlib.sha256()
    for kind, data in pieces:
        canonical = data if kind == b"J" else _IMAGE_NAME.sub(b"/FormXob.*", data)
        digest.update(kind + len(canonical).to_bytes(8, "big") + canonical)
    return digest.hexdigest()
