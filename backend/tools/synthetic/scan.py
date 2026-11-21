"""PDF escaneados: una imagen por página, sin capa de texto (decisión de Borja, 20/11/2026).

Se rasteriza el PDF vectorial con PDFium (``pypdfium2``, que trae su propio
motor de fuentes, así que no depende de las del sistema) y se degrada con
Pillow como un escáner de oficina: menos contraste, un poco de desenfoque,
grano, una ligera rotación y alguna mota. El ruido sale de ``random.Random``
con la semilla del documento, no de ``Image.effect_noise``, que usa el
``rand()`` de C y no se puede sembrar.

La imagen va en JPEG en escala de grises (ReportLab la incrusta tal cual, con
DCTDecode), para que todo ``samples/`` quepa en unos 10 MB.

Cómo se liga un escaneado con lo regenerado, sin depender de los bytes del
JPEG, que cambian con la versión de libjpeg de cada plataforma:

- su ``content_sha256`` (``fingerprint.content_fingerprint``) cubre todo el PDF
  menos los datos del JPEG, que sustituye por un marcador: estructura, metadatos,
  flujo de contenido y dimensiones de la imagen;
- los metadatos (``/Keywords``) llevan el ``content_sha256`` del PDF vectorial
  que se rasterizó (``source_fingerprint``), y todos (``scan_metadata``) tienen
  que ser los regenerados;
- ``scan_differences`` compara dos escaneados página a página: mismas
  dimensiones de la imagen y como mucho ``MAX_INK_MISMATCH`` píxeles en los que
  uno tenga tinta y el otro papel. Medido con la semilla por defecto: recodificar
  el JPEG a calidad 20 o 90, rasterizar sin suavizado de texto o cambiar el
  desenfoque dan 0 píxeles así; desplazar la imagen un píxel da unos 4.000, otra
  semilla de ruido unos 50.000 y otro documento, de 60.000 a 200.000.
"""

import random
import re
from io import BytesIO

import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from reportlab.lib.utils import ImageReader

from synthetic.pdfkit import PAGE_HEIGHT, PAGE_WIDTH, PDF_KEYWORDS, new_canvas

SCAN_DPI = 150
JPEG_QUALITY = 45
_POINTS_PER_INCH = 72
# Papel algo gris y tinta algo clara: contraste de un escáner barato.
_PAPER = 232
_INK = 40
_GRAIN = 0.06
_BLUR = 0.6
_ANGLES = (-1.3, -0.9, -0.6, -0.4, 0.4, 0.6, 0.8, 1.1)

SOURCE_KEYWORD = "kapataz-origen-sha256"
_SOURCE = re.compile(rf"{SOURCE_KEYWORD}:([0-9a-f]{{64}})")
# Diferencia de gris a partir de la cual un píxel es tinta en uno y papel en el otro
# (el papel está en 232 y la tinta en 40), y cuántos de esos píxeles se toleran.
_INK_DELTA = 96
MAX_INK_MISMATCH = 20


def scan_pdf(vector_pdf: bytes, *, seed: int, title: str, source_fingerprint: str) -> bytes:
    """Versión escaneada de un PDF vectorial: misma paginación, solo imágenes.

    ``source_fingerprint`` es el ``content_sha256`` de ``vector_pdf``; queda en los
    metadatos para ligar el escaneado con su fuente.
    """
    rng = random.Random(seed)  # noqa: S311 - ruido de imagen, no criptografía
    buffer = BytesIO()
    keywords = f"{PDF_KEYWORDS}, {SOURCE_KEYWORD}:{source_fingerprint}"
    canvas = new_canvas(buffer, title, keywords=keywords)
    for page in _rasterize(vector_pdf):
        jpeg = BytesIO()
        _degrade(page, rng).save(jpeg, format="JPEG", quality=JPEG_QUALITY, optimize=False)
        jpeg.seek(0)
        canvas.drawImage(ImageReader(jpeg), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _rasterize(vector_pdf: bytes) -> list[Image.Image]:
    document = pdfium.PdfDocument(vector_pdf)
    pages: list[Image.Image] = []
    try:
        for index in range(len(document)):
            page = document[index]
            bitmap = page.render(scale=SCAN_DPI / _POINTS_PER_INCH, grayscale=True)
            image: Image.Image = bitmap.to_pil()
            pages.append(image.convert("L").copy())
            bitmap.close()
            page.close()
    finally:
        document.close()
    return pages


def _degrade(page: Image.Image, rng: random.Random) -> Image.Image:
    lut = [_INK + (value * (_PAPER - _INK)) // 255 for value in range(256)]
    image = page.point(lut).filter(ImageFilter.GaussianBlur(_BLUR))
    noise = Image.frombytes("L", image.size, rng.randbytes(image.size[0] * image.size[1]))
    image = Image.blend(image, noise, _GRAIN)
    image = image.rotate(
        rng.choice(_ANGLES),
        resample=Image.Resampling.BICUBIC,
        expand=False,
        fillcolor=_PAPER,
    )
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for _ in range(rng.randint(3, 9)):
        x, y = rng.randint(0, width - 1), rng.randint(0, height - 1)
        radius = rng.randint(1, 3)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rng.randint(60, 140))
    return image


def scan_metadata(pdf: bytes) -> dict[str, str]:
    """El diccionario ``/Info`` según PDFium: título, asunto, autor, palabras clave…"""
    document = pdfium.PdfDocument(pdf)
    try:
        return {str(key): str(value) for key, value in document.get_metadata_dict().items()}
    finally:
        document.close()


def scan_source(scanned_pdf: bytes) -> str | None:
    """El ``content_sha256`` de la fuente que declaran los metadatos del escaneado."""
    match = _SOURCE.search(scan_metadata(scanned_pdf).get("Keywords", ""))
    return match.group(1) if match else None


def page_images(scanned_pdf: bytes) -> list[list[Image.Image]]:
    """Las imágenes de cada página, decodificadas a su tamaño en píxeles y en gris."""
    document = pdfium.PdfDocument(scanned_pdf)
    pages: list[list[Image.Image]] = []
    try:
        for index in range(len(document)):
            page = document[index]
            images: list[Image.Image] = []
            for item in page.get_objects():
                if isinstance(item, pdfium.PdfImage):
                    # La copia no comparte memoria con el mapa de bits de PDFium, que se
                    # libera con la página (cerrarlo a mano avisa de un posible uso tras liberar).
                    image: Image.Image = item.get_bitmap(render=False).to_pil()
                    images.append(image.convert("L").copy())
            pages.append(images)
            page.close()
    finally:
        document.close()
    return pages


def scan_differences(expected: bytes, actual: bytes) -> list[str]:
    """En qué no coinciden dos escaneados: páginas, imágenes, dimensiones o tinta."""
    wanted, found = page_images(expected), page_images(actual)
    if len(wanted) != len(found):
        return [f"{len(found)} páginas en vez de {len(wanted)}"]
    problems: list[str] = []
    for number, (want, have) in enumerate(zip(wanted, found, strict=True), start=1):
        if len(want) != len(have):
            problems.append(f"página {number}: {len(have)} imágenes en vez de {len(want)}")
            continue
        for left, right in zip(want, have, strict=True):
            if left.size != right.size:
                problems.append(f"página {number}: imagen de {right.size} en vez de {left.size}")
            elif (pixels := ink_mismatch(left, right)) > MAX_INK_MISMATCH:
                problems.append(f"página {number}: la imagen no coincide ({pixels} píxeles)")
    return problems


def ink_mismatch(left: Image.Image, right: Image.Image) -> int:
    """Píxeles que son tinta en una imagen y papel en la otra."""
    histogram = ImageChops.difference(left, right).histogram()
    return sum(histogram[_INK_DELTA:])
