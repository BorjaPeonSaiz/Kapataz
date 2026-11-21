"""API de datos del generador sintético: determinismo, contenido y paso al dominio (ADR-020).

Prueban ``build_dataset`` sin E/S: lo que ``seed_demo.py`` cargará en el
espacio de demostración (RF-CF-04) y lo que hay detrás de cada PDF.
"""

from __future__ import annotations

import dataclasses
import random
import re
from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from kapataz.domain.billing.calculation import totals_from_lines
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage
from kapataz.domain.billing.quote import QuoteStatus
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.domain.customers.tax_id import TaxId, TaxIdKind
from synthetic.amounts import compute_totals
from synthetic.build import DEFAULT_SEED, PERIOD_END, PERIOD_START, build_dataset
from synthetic.model import (
    MAIN_LAYOUTS,
    DocumentType,
    Layout,
    SeededErrorKind,
    Trade,
    TrapTechnique,
)
from synthetic.output import render_all
from synthetic.people import FAKE_BANK_CODE, email, iban, phone
from synthetic.planning import SCANNED_PERCENT
from tests.unit.tools.synthetic_support import assert_unreachable_phones

if TYPE_CHECKING:
    from synthetic.model import SyntheticDataset

# Marcadores de requisito (convención «Sin req» del repositorio): lo que carga
# seed_demo.py en el espacio de demostración (profesional, clientes, catálogo y
# presupuestos) lleva RF-CF-04. El histórico de facturas y el plan de los PDF solo
# alimentan las evaluaciones de la ingesta: esas pruebas verifican el dataset, no
# RF-IN-02, RF-IN-05, RF-FA-05, RN-F-05 ni RN-F-13, que se prueban contra la app.


def _walk(value: object) -> list[object]:
    """Todos los valores de un dataclass anidado, para buscar floats."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        found: list[object] = []
        for item in dataclasses.fields(value):
            found.extend(_walk(getattr(value, item.name)))
        return found
    if isinstance(value, tuple | list):
        return [inner for item in value for inner in _walk(item)]
    return [value]


# ------------------------------------------------------------------ determinismo


@pytest.mark.req("RF-CF-04")
def test_la_misma_semilla_produce_el_mismo_dataset(dataset: SyntheticDataset) -> None:
    assert build_dataset(DEFAULT_SEED) == dataset


@pytest.mark.req("RF-CF-04")
def test_otra_semilla_produce_otro_dataset(dataset: SyntheticDataset) -> None:
    other = build_dataset(DEFAULT_SEED + 1)
    assert other != dataset
    assert other.professionals[0].professional.name != dataset.professionals[0].professional.name


@pytest.mark.req("RF-CF-04")
def test_ningun_importe_es_float(dataset: SyntheticDataset) -> None:
    values = _walk(dataset)
    assert not [value for value in values if isinstance(value, float)]
    assert any(isinstance(value, Decimal) for value in values)


# ------------------------------------------------------------------ actividad


@pytest.mark.req("RF-CF-04")
def test_dos_profesionales_con_18_meses_de_actividad(dataset: SyntheticDataset) -> None:
    assert [p.professional.trade for p in dataset.professionals] == [
        Trade.ELECTRICIAN,
        Trade.BRICKLAYER,
    ]
    assert (dataset.period_start, dataset.period_end) == (PERIOD_START, PERIOD_END)
    months = (PERIOD_END.year - PERIOD_START.year) * 12 + PERIOD_END.month - PERIOD_START.month + 1
    assert months == 18
    for data in dataset.professionals:
        assert 40 <= len(data.invoices) <= 60
        assert 20 <= len(data.quotes) <= 30
        dates = [i.issue_date for i in data.invoices] + [q.issue_date for q in data.quotes]
        assert all(PERIOD_START <= when <= PERIOD_END for when in dates)
        assert all(when.weekday() < 5 for when in dates)


@pytest.mark.req("RF-CF-04")
def test_numeracion_correlativa_por_serie_y_anio_en_orden_de_fecha(
    dataset: SyntheticDataset,
) -> None:
    for data in dataset.professionals:
        p = data.professional
        for series, items in (
            (p.invoice_series, [(i.number, i.issue_date) for i in data.invoices]),
            (p.quote_series, [(q.number, q.issue_date) for q in data.quotes]),
        ):
            by_year: dict[int, list[tuple[DocumentNumber, object]]] = {}
            for number, when in items:
                parsed = DocumentNumber.parse(number)
                assert parsed.series.code == series
                assert parsed.year == when.year
                by_year.setdefault(parsed.year, []).append((parsed, when))
            for numbered in by_year.values():
                numbered.sort(key=lambda item: item[0].sequence)
                assert [n.sequence for n, _ in numbered] == list(range(1, len(numbered) + 1))
                issued = [when for _, when in numbered]
                assert issued == sorted(issued)


@pytest.mark.req("RF-CF-04")
def test_las_facturas_de_un_presupuesto_lo_citan_y_son_posteriores(
    dataset: SyntheticDataset,
) -> None:
    for data in dataset.professionals:
        quotes = {q.number: q for q in data.quotes}
        for invoice in data.invoices:
            if invoice.quote_number is None:
                continue
            quote = quotes[invoice.quote_number]
            assert quote.status in {QuoteStatus.INVOICED, QuoteStatus.PARTIALLY_INVOICED}
            assert invoice.issue_date > quote.issue_date
            assert invoice.customer_key == quote.customer_key
        invoiced = {i.quote_number for i in data.invoices if i.quote_number}
        for quote in data.quotes:
            billed = quote.status in {QuoteStatus.INVOICED, QuoteStatus.PARTIALLY_INVOICED}
            assert billed == (quote.number in invoiced)


@pytest.mark.req("RF-CF-04")
def test_catalogo_de_referencia_con_precios_coherentes(dataset: SyntheticDataset) -> None:
    for data in dataset.professionals:
        catalog = {entry.key: entry for entry in data.catalog}
        assert len(catalog) >= 15
        for document in (*data.quotes, *data.invoices):
            for line in document.lines:
                if line.catalog_key is None:
                    continue
                reference = catalog[line.catalog_key].reference_price
                # Del -8 % al +10 % y un 3 % más el segundo año, más el redondeo a 0,50 €.
                assert reference * Decimal("0.90") <= line.unit_price <= reference * Decimal("1.15")
                assert line.unit == catalog[line.catalog_key].unit


# ------------------------------------------------------------------ fiscalidad


# Sin req: verifica las reglas fiscales del histórico de evaluación, no RF-FA-05 ni RN-F-05.
def test_el_albanil_factura_a_constructoras_con_inversion_y_retencion(
    dataset: SyntheticDataset,
) -> None:
    bricklayer = dataset.professional(Trade.BRICKLAYER)
    reverse = [i for i in bricklayer.invoices if i.reverse_charge]
    assert len(reverse) >= len(bricklayer.invoices) // 2
    for invoice in bricklayer.invoices:
        customer = bricklayer.customer(invoice.customer_key)
        assert invoice.reverse_charge == customer.is_contractor
        assert all((line.vat_rate is None) == invoice.reverse_charge for line in invoice.lines)
        is_business = customer.recipient_type is RecipientType.BUSINESS
        assert (invoice.withholding_rate == Decimal(1)) == is_business
    assert any(i.guarantee_rate == Decimal(5) for i in bricklayer.invoices)


# Sin req: verifica el histórico de evaluación, no RF-FA-05 ni RN-F-13.
def test_el_electricista_usa_iva_general_y_reducido_sin_retencion(
    dataset: SyntheticDataset,
) -> None:
    electrician = dataset.professional(Trade.ELECTRICIAN)
    rates = Counter(line.vat_rate for i in electrician.invoices for line in i.lines)
    assert set(rates) == {Decimal(10), Decimal(21)}
    for invoice in electrician.invoices:
        assert invoice.withholding_rate is None
        assert not invoice.reverse_charge
        customer = electrician.customer(invoice.customer_key)
        works = {line.vat_rate for line in invoice.lines if not line.outside_works}
        if customer.recipient_type is RecipientType.BUSINESS:
            assert works == {Decimal(21)}
    mixed = [i for i in electrician.invoices if len({line.vat_rate for line in i.lines}) > 1]
    assert len(mixed) == 3


# Sin req: comprueba que el generador calcula como el dominio; RN-03 lo prueba el dominio.
def test_los_totales_de_un_solo_tipo_coinciden_con_los_del_dominio(
    dataset: SyntheticDataset,
) -> None:
    compared = 0
    for data in dataset.professionals:
        documents = [
            (i.lines, i.reverse_charge, i.withholding_rate, i.guarantee_rate) for i in data.invoices
        ]
        documents += [(q.lines, q.reverse_charge, None, None) for q in data.quotes]
        for lines, reverse_charge, withholding_rate, guarantee_rate in documents:
            rates = {line.vat_rate for line in lines}
            if len(rates) != 1:
                continue
            (rate,) = rates
            ours = compute_totals(
                lines,
                reverse_charge=reverse_charge,
                withholding_rate=withholding_rate,
                guarantee_rate=guarantee_rate,
            )
            treatment = (
                VatTreatment.reverse_charge() if rate is None else VatTreatment.taxed(TaxRate(rate))
            )
            domain = totals_from_lines(
                [Money(line.amount) for line in lines],
                treatment,
                None if withholding_rate is None else Percentage(withholding_rate),
                None if guarantee_rate is None else Percentage(guarantee_rate),
            )
            assert ours.base == domain.base.amount
            assert ours.vat_amount == domain.tax.amount
            assert (ours.withholding or Decimal(0)) == domain.withholding.amount
            assert (ours.guarantee or Decimal(0)) == domain.guarantee.amount
            # El total impreso es base + cuota - IRPF: el «collectible» del dominio.
            assert ours.total == domain.collectible.amount
            assert ours.amount_due == domain.amount_due.amount
            compared += 1
    assert compared > 100


# ------------------------------------------------------------------ clientes


@pytest.mark.req("RF-CF-04")
def test_los_nif_pasan_el_dominio_con_el_tipo_de_entidad_correcto(
    dataset: SyntheticDataset,
) -> None:
    for data in dataset.professionals:
        assert TaxId(data.professional.tax_id).kind is TaxIdKind.DNI
        seen = [data.professional.tax_id]
        for customer in data.customers:
            tax_id = TaxId(customer.tax_id)
            seen.append(customer.tax_id)
            match customer.recipient_type:
                case RecipientType.PRIVATE:
                    assert tax_id.kind is TaxIdKind.DNI
                case RecipientType.COMMUNITY:
                    assert tax_id.kind is TaxIdKind.CIF
                    assert customer.tax_id.startswith("H")
                case RecipientType.BUSINESS:
                    assert tax_id.kind is TaxIdKind.CIF
                    assert customer.tax_id.startswith("B")
        assert len(set(seen)) == len(seen)


@pytest.mark.req("RF-CF-04")
def test_hay_particulares_con_el_mismo_nombre_y_distinto_nif(
    dataset: SyntheticDataset,
) -> None:
    for data in dataset.professionals:
        privates = [c for c in data.customers if c.recipient_type is RecipientType.PRIVATE]
        names = Counter(c.name for c in privates)
        twins = [name for name, count in names.items() if count == 2]
        assert len(twins) == 1
        pair = [c for c in privates if c.name == twins[0]]
        assert pair[0].tax_id != pair[1].tax_id
        assert pair[0].address != pair[1].address
        used = {d.customer_key for d in (*data.invoices, *data.quotes)}
        assert {c.key for c in pair} <= used


@pytest.mark.req("RF-CF-04")
def test_hay_comunidades_y_constructoras_de_nombre_parecido(dataset: SyntheticDataset) -> None:
    electrician = dataset.professional(Trade.ELECTRICIAN)
    communities = [c for c in electrician.customers if c.recipient_type is RecipientType.COMMUNITY]
    first, second = communities[0], communities[1]
    street = re.sub(r" \d+$", "", first.name)
    assert second.name.startswith(street)
    assert first.name != second.name
    numbers = [first.name.rsplit(" ", 1)[1], second.name.rsplit(" ", 1)[1]]
    assert numbers[0] == numbers[1][::-1]
    bricklayer = dataset.professional(Trade.BRICKLAYER)
    surname = bricklayer.customers[0].name.split()[1]
    assert any(c.name == f"Construcciones y Reformas {surname} S.L." for c in bricklayer.customers)


# ------------------------------------------------------------------ estados


@pytest.mark.req("RF-CF-04")
def test_los_presupuestos_cubren_los_estados_de_un_historico(dataset: SyntheticDataset) -> None:
    statuses = Counter(q.status for data in dataset.professionals for q in data.quotes)
    for status in (
        QuoteStatus.INVOICED,
        QuoteStatus.REJECTED,
        QuoteStatus.EXPIRED,
        QuoteStatus.PARTIALLY_INVOICED,
    ):
        assert statuses[status] >= 1


# ------------------------------------------------------------------ documentos


# Sin req: verifica el plan de los PDF de evaluación de RF-IN-02 y RF-IN-05, no el requisito.
def test_reparto_de_maquetaciones_escaneados_errores_trampas_y_otros(
    dataset: SyntheticDataset,
) -> None:
    expected_errors = {
        SeededErrorKind.SPLIT_LINE: 2,
        SeededErrorKind.TOTAL_MISMATCH: 2,
        SeededErrorKind.VAT_MISMATCH: 2,
        SeededErrorKind.BASE_MISMATCH: 1,
        SeededErrorKind.MISSING_TAX_ID: 2,
    }
    for data in dataset.professionals:
        docs = data.documents
        assert len(docs) == len(data.invoices) + len(data.quotes) + 4
        assert Counter(d.document_type for d in docs)[DocumentType.OTHER] == 4
        layouts = Counter(d.layout for d in docs if d.document_type is not DocumentType.OTHER)
        assert set(layouts) == set(MAIN_LAYOUTS)
        assert max(layouts.values()) - min(layouts.values()) <= 3
        scanned = [d for d in docs if d.scanned]
        assert len(scanned) == (len(docs) * SCANNED_PERCENT + 50) // 100
        assert {d.layout for d in scanned} >= set(MAIN_LAYOUTS)
        assert any(d.seeded_error is not None for d in scanned)
        errors = Counter(d.seeded_error for d in docs if d.seeded_error is not None)
        assert errors == expected_errors
        for doc in docs:
            assert re.fullmatch(r"doc-\d{3}", doc.doc_id)
            assert not (doc.trap and doc.seeded_error)
            if doc.document_type is DocumentType.OTHER:
                assert doc.seeded_error is None
            else:
                assert doc.layout is not Layout.LETTER
    traps = Counter(
        (d.trap.technique, d.scanned)
        for data in dataset.professionals
        for d in data.documents
        if d.trap
    )
    assert traps == {
        (TrapTechnique.VISIBLE_FOOTER, False): 1,
        (TrapTechnique.VISIBLE_FOOTER, True): 1,
        (TrapTechnique.HIDDEN_TEXT, False): 1,
        (TrapTechnique.LINE_CONCEPT, False): 1,
        (TrapTechnique.METADATA, False): 1,
    }


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("seed", [1, 9, 42])
def test_otras_semillas_tambien_cumplen_el_plan(seed: int) -> None:
    """La semilla 9 llenaba el objetivo de facturas solo con certificaciones."""
    other = build_dataset(seed)
    for data in other.professionals:
        assert 40 <= len(data.invoices) <= 60
        assert 20 <= len(data.quotes) <= 30
        used = {d.customer_key for d in (*data.invoices, *data.quotes)}
        assert used == {c.key for c in data.customers}
    special = render_all(
        other,
        select=lambda spec: (
            spec.trap is not None or spec.seeded_error is SeededErrorKind.SPLIT_LINE
        ),
    )
    # Cinco trampas y dos líneas partidas por profesional.
    assert len(special) == 9
    assert all(item.info.split_lines for item in special if item.spec.trap is None)


# ------------------------------------------------------------------ contacto ficticio

_EMAIL = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_PHONE = re.compile(r"(?<!\d)\d{3} \d{2} \d{2} \d{2}(?!\d)")
_IBAN = re.compile(r"\bES\d{2}(?: \d{4}){5}\b")
_FAKE_PHONE = re.compile(r"4[69]\d \d{2} \d{2} \d{2}")


def _mod97(value: str) -> int:
    compact = value.replace(" ", "")
    rearranged = compact[4:] + compact[:4]
    return int("".join(str(int(ch, 36)) for ch in rearranged)) % 97


def _texts(dataset: SyntheticDataset) -> list[str]:
    return [value for value in _walk(dataset) if isinstance(value, str)]


# Sin req: fijan que los datos de contacto del dataset no pueden ser de nadie (ADR-020).
def test_los_correos_solo_usan_dominios_reservados(dataset: SyntheticDataset) -> None:
    domains = {match.group(1) for text in _texts(dataset) for match in _EMAIL.finditer(text)}
    assert domains
    assert all(d.endswith(".example") or d == "example.com" for d in domains), domains
    assert email("Electricidad Ñandú").endswith("@correo.example")


# Sin req: fija el patrón ficticio de los teléfonos (ADR-020).
def test_los_telefonos_son_del_segmento_sin_atribuir_y_no_se_pueden_marcar(
    dataset: SyntheticDataset,
) -> None:
    found = {match.group(0) for text in _texts(dataset) for match in _PHONE.finditer(text)}
    phones = {p.professional.phone for p in dataset.professionals}
    assert phones <= found
    assert all(_FAKE_PHONE.fullmatch(value) for value in found), found
    for text in _texts(dataset):
        assert_unreachable_phones(text, text)
    rng = random.Random(0)
    for _ in range(500):
        assert phone(rng, mobile=True).startswith("46")
        assert phone(rng, mobile=False).startswith("49")


# Sin req: fija la entidad inexistente de los IBAN y su mod 97 (ADR-020).
def test_los_iban_son_de_una_entidad_inexistente_con_control_valido(
    dataset: SyntheticDataset,
) -> None:
    assert FAKE_BANK_CODE == "0000"
    found = {match.group(0) for text in _texts(dataset) for match in _IBAN.finditer(text)}
    professional = {p.professional.iban for p in dataset.professionals}
    assert professional <= found
    for value in found:
        if value in professional:
            assert _mod97(value) == 1, value
            assert value.replace(" ", "")[4:8] == FAKE_BANK_CODE
        else:
            # Los de las trampas: dígitos de control 00, que el mod 97 nunca da.
            assert value.startswith("ES00")
            assert _mod97(value) != 1
    rng = random.Random(0)
    for _ in range(500):
        value = iban(rng)
        assert _mod97(value) == 1
        assert value.replace(" ", "")[4:8] == FAKE_BANK_CODE
