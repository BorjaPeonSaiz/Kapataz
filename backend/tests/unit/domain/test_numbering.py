"""Series y números de documento (RF-FA-02, RF-PR-05, RN-F-01, RN-F-04, RN-F-06)."""

from datetime import date

import pytest

from kapataz.domain.billing.errors import (
    InvalidDocumentNumberError,
    InvalidSeriesError,
    IssueDateBeforeLastError,
)
from kapataz.domain.billing.numbering import (
    DocumentNumber,
    Series,
    check_issue_date,
    next_number,
)


@pytest.mark.req("RF-FA-02")
def test_series_por_defecto():
    assert str(Series.invoices()) == "F"
    assert str(Series.correctives()) == "R"
    assert str(Series.quotes()) == "P"


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("code", ["", "f", "1F", "F-1", "ABCDEFGHIJK", "Ñ"])
def test_series_no_validas(code):
    with pytest.raises(InvalidSeriesError):
        Series(code)


@pytest.mark.req("RF-FA-02")
@pytest.mark.req("RF-PR-05")
@pytest.mark.parametrize(
    ("series", "sequence", "text"),
    [("F", 1, "F-2026-0001"), ("P", 42, "P-2026-0042"), ("R", 12345, "R-2026-12345")],
)
def test_formato_del_numero(series, sequence, text):
    number = DocumentNumber(Series(series), 2026, sequence)
    assert str(number) == text
    assert DocumentNumber.parse(text) == number


@pytest.mark.req("RN-F-06")
def test_serie_y_numero_no_pasan_de_60_caracteres():
    long_series = Series("ABCDEFGHIJ")
    ok = DocumentNumber(long_series, 2026, 10**43)
    assert len(str(ok)) == 60
    with pytest.raises(InvalidDocumentNumberError):
        DocumentNumber(long_series, 2026, 10**44)


@pytest.mark.req("RF-FA-02")
@pytest.mark.parametrize(
    ("year", "sequence"),
    [(1999, 1), (10000, 1), (2026, 0), (2026, -1)],
)
def test_numeros_fuera_de_rango(year, sequence):
    with pytest.raises(InvalidDocumentNumberError):
        DocumentNumber(Series("F"), year, sequence)


@pytest.mark.req("RF-FA-02")
@pytest.mark.parametrize("raw", ["F-2026-1", "F-2026-00001", "F2026-0001", "f-2026-0001", ""])
def test_numeros_no_normalizados(raw):
    with pytest.raises(InvalidDocumentNumberError):
        DocumentNumber.parse(raw)


@pytest.mark.req("RN-F-01")
def test_siguiente_numero_sin_huecos():
    series = Series.invoices()
    first = next_number(series, 2026, None)
    assert str(first) == "F-2026-0001"
    assert str(next_number(series, 2026, first)) == "F-2026-0002"
    assert DocumentNumber.parse("F-2026-0007").next() == DocumentNumber.parse("F-2026-0008")


@pytest.mark.req("RN-F-01")
@pytest.mark.parametrize("last", ["R-2026-0003", "F-2025-0003"])
def test_el_contador_es_por_serie_y_anio(last):
    with pytest.raises(InvalidDocumentNumberError):
        next_number(Series.invoices(), 2026, DocumentNumber.parse(last))


@pytest.mark.req("RN-F-01")
def test_los_numeros_se_ordenan_dentro_de_la_serie():
    numbers = [DocumentNumber.parse(n) for n in ["F-2026-0010", "F-2026-0002", "F-2025-0099"]]
    assert [str(n) for n in sorted(numbers)] == ["F-2025-0099", "F-2026-0002", "F-2026-0010"]


@pytest.mark.req("RN-F-04")
def test_fecha_igual_o_posterior_a_la_ultima():
    check_issue_date(date(2026, 3, 1), None)
    check_issue_date(date(2026, 3, 1), date(2026, 3, 1))
    check_issue_date(date(2026, 3, 2), date(2026, 3, 1))


@pytest.mark.req("RN-F-04")
def test_fecha_anterior_a_la_ultima_se_rechaza():
    with pytest.raises(IssueDateBeforeLastError, match="2026-02-28"):
        check_issue_date(date(2026, 2, 28), date(2026, 3, 1))
