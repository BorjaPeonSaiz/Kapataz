"""Series y números de documento (RF-FA-02, RF-PR-05, RN-F-01, RN-F-04, RN-F-06).

El número se asigna al emitir, con el contador de la serie bloqueado en la base
de datos (RN-F-01). El dominio solo define cómo es un número válido, cuál es el
siguiente y si una fecha de expedición es admisible.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Self

from kapataz.domain.aeat_limits import MAX_SERIES_NUMBER_LENGTH
from kapataz.domain.billing.errors import (
    InvalidDocumentNumberError,
    InvalidSeriesError,
    IssueDateBeforeLastError,
)

# Letras mayúsculas y cifras: el número se imprime, se dicta y se envía a la
# AEAT, y un código corto sin signos evita confusiones en los tres sitios.
_SERIES_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,9}$")
_NUMBER_PATTERN = re.compile(r"^([A-Z][A-Z0-9]{0,9})-(\d{4})-(\d{4,})$")
MIN_YEAR = 2000
MAX_YEAR = 9999
# Cuatro cifras como mínimo, como en F-2026-0001; si una cuenta pasa de 9.999
# facturas en un año, el número crece sin romper el orden dentro del año.
_SEQUENCE_WIDTH = 4


@dataclass(frozen=True, slots=True, order=True)
class Series:
    """Serie de numeración: F (facturas), R (rectificativas), P (presupuestos)…"""

    code: str

    INVOICE: ClassVar[str] = "F"
    CORRECTIVE: ClassVar[str] = "R"
    QUOTE: ClassVar[str] = "P"

    def __post_init__(self) -> None:
        if not _SERIES_PATTERN.fullmatch(self.code):
            msg = "Una serie son de 1 a 10 letras mayúsculas o cifras y empieza por letra."
            raise InvalidSeriesError(msg)

    @classmethod
    def invoices(cls) -> Self:
        return cls(cls.INVOICE)

    @classmethod
    def correctives(cls) -> Self:
        return cls(cls.CORRECTIVE)

    @classmethod
    def quotes(cls) -> Self:
        return cls(cls.QUOTE)

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True, order=True)
class DocumentNumber:
    """Número completo de un documento: serie, año y secuencia (``F-2026-0001``).

    La secuencia es correlativa por cuenta, serie y año (RN-F-01). La serie y
    el número juntos no pasan de 60 caracteres (RN-F-06).
    """

    series: Series
    year: int
    sequence: int

    def __post_init__(self) -> None:
        if not MIN_YEAR <= self.year <= MAX_YEAR:
            raise InvalidDocumentNumberError("Año fuera de rango.")
        if self.sequence < 1:
            raise InvalidDocumentNumberError("La secuencia empieza en 1.")
        if len(str(self)) > MAX_SERIES_NUMBER_LENGTH:
            msg = f"La serie y el número juntos no pueden pasar de {MAX_SERIES_NUMBER_LENGTH}."
            raise InvalidDocumentNumberError(msg)

    @classmethod
    def first(cls, series: Series, year: int) -> Self:
        return cls(series, year, 1)

    @classmethod
    def parse(cls, raw: str) -> Self:
        match = _NUMBER_PATTERN.fullmatch(raw)
        if match is None:
            raise InvalidDocumentNumberError("Número de documento no válido.")
        series, year, sequence = match.groups()
        number = cls(Series(series), int(year), int(sequence))
        # Rechaza ceros de más («F-2026-00001»): dos textos no pueden ser el mismo número.
        if str(number) != raw:
            raise InvalidDocumentNumberError("Número de documento no normalizado.")
        return number

    def next(self) -> "DocumentNumber":
        return DocumentNumber(self.series, self.year, self.sequence + 1)

    def __str__(self) -> str:
        return f"{self.series.code}-{self.year}-{self.sequence:0{_SEQUENCE_WIDTH}d}"


def next_number(series: Series, year: int, last: DocumentNumber | None) -> DocumentNumber:
    """Siguiente número de la serie y el año, a partir del último emitido.

    El caso de uso lo llama con el contador ya bloqueado (RN-F-01). Si el último
    es de otra serie o de otro año es un error de quien llama, no un salto de
    año: el contador es por cuenta, serie y año.
    """
    if last is None:
        return DocumentNumber.first(series, year)
    if last.series != series or last.year != year:
        raise InvalidDocumentNumberError("El último número no es de esta serie y año.")
    return last.next()


def check_issue_date(issue_date: date, last_issue_date: date | None) -> None:
    """RN-F-04: la fecha de expedición no es anterior a la última de la serie.

    Se llama con el contador de la serie ya bloqueado, para que otra emisión
    no pueda colarse entre la comprobación y el número.
    """
    if last_issue_date is not None and issue_date < last_issue_date:
        msg = (
            f"La fecha de expedición ({issue_date.isoformat()}) es anterior a la de la "
            f"última factura emitida de la serie ({last_issue_date.isoformat()})."
        )
        raise IssueDateBeforeLastError(msg)
