"""Presupuestos con versiones, estados y origen del precio (RF-PR-04, RN-06, RN-07)."""

import dataclasses
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.codes import LineOrigin, RecipientType
from kapataz.domain.billing.errors import (
    InvalidAmountError,
    InvalidQuoteError,
    InvalidQuoteTransitionError,
    QuoteNotEditableError,
)
from kapataz.domain.billing.ids import QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.quote import (
    PriceSource,
    PriceSourceKind,
    Quote,
    QuoteLine,
    QuoteStatus,
    QuoteVersion,
)
from kapataz.domain.billing.works_vat import material_share
from kapataz.domain.customers.model import CustomerId
from tests.unit.domain.billing_factories import money

NOW = datetime(2026, 11, 18, tzinfo=UTC)


def quote_line(price: str | None = "45.00", quantity: str = "3", **kwargs: object) -> QuoteLine:
    source = PriceSource.manual() if price is not None else PriceSource.none()
    values: dict[str, object] = {
        "id": QuoteLineId(uuid4()),
        "description": "Punto de luz",
        "quantity": Quantity.of(quantity),
        "unit_price": None if price is None else money(price),
        "price_source": source,
    } | kwargs
    return QuoteLine(**values)  # type: ignore[arg-type]


def version(number: int = 1, *lines: QuoteLine, valid_until: date | None = None) -> QuoteVersion:
    return QuoteVersion(
        id=QuoteVersionId(uuid4()),
        version=number,
        lines=lines or (quote_line(),),
        recipient_type=RecipientType.PRIVATE,
        dwelling_over_two_years=True,
        valid_until=valid_until,
        created_at=NOW,
    )


def quote(status: QuoteStatus = QuoteStatus.DRAFT, *versions: QuoteVersion) -> Quote:
    return Quote(
        id=QuoteId(uuid4()),
        tenant_id=TenantId(uuid4()),
        customer_id=CustomerId(uuid4()),
        number=DocumentNumber.parse("P-2026-0001"),
        status=status,
        versions=versions or (version(),),
        created_at=NOW,
    )


@pytest.mark.req("RF-PR-04")
def test_ciclo_completo_de_estados():
    sent = quote().send()
    assert sent.status is QuoteStatus.SENT
    accepted = sent.accept()
    assert accepted.is_billable
    partially = accepted.mark_partially_invoiced()
    assert partially.status is QuoteStatus.PARTIALLY_INVOICED
    assert partially.mark_partially_invoiced().is_billable
    assert partially.mark_invoiced().status is QuoteStatus.INVOICED
    assert accepted.mark_invoiced().status is QuoteStatus.INVOICED
    assert sent.reject().status is QuoteStatus.REJECTED


@pytest.mark.req("RF-PR-07")
@pytest.mark.parametrize(
    "status",
    [QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.REJECTED, QuoteStatus.EXPIRED],
)
def test_solo_se_factura_un_presupuesto_aceptado(status):
    pending = quote(status)
    assert not pending.is_billable
    with pytest.raises(InvalidQuoteTransitionError):
        pending.mark_invoiced()


@pytest.mark.req("RF-PR-04")
@pytest.mark.parametrize(
    ("status", "transition"),
    [
        (QuoteStatus.DRAFT, Quote.accept),
        (QuoteStatus.DRAFT, Quote.reject),
        (QuoteStatus.SENT, Quote.send),
        (QuoteStatus.INVOICED, Quote.mark_partially_invoiced),
        (QuoteStatus.REJECTED, Quote.accept),
    ],
)
def test_transiciones_no_permitidas(status, transition):
    with pytest.raises(InvalidQuoteTransitionError):
        transition(quote(status))


@pytest.mark.req("RF-PR-04")
def test_caduca_un_enviado_pasada_su_validez():
    sent = quote(QuoteStatus.SENT, version(valid_until=date(2026, 12, 1)))
    with pytest.raises(InvalidQuoteTransitionError):
        sent.expire(date(2026, 12, 1))
    assert sent.expire(date(2026, 12, 2)).status is QuoteStatus.EXPIRED
    with pytest.raises(InvalidQuoteTransitionError):
        quote(QuoteStatus.SENT).expire(date(2030, 1, 1))


@pytest.mark.req("RF-PR-04")
def test_editar_un_borrador_sustituye_su_version():
    draft = quote()
    revised = draft.revise(version(1, quote_line("50.00")))
    assert len(revised.versions) == 1
    assert revised.current_version.base == money("150.00")


@pytest.mark.req("RF-PR-04")
def test_modificar_un_enviado_crea_una_version_nueva():
    sent = quote(QuoteStatus.SENT)
    assert sent.revision_number == 2
    revised = sent.revise(version(2, quote_line("50.00")))
    assert [v.version for v in revised.versions] == [1, 2]
    assert revised.status is QuoteStatus.DRAFT
    assert revised.versions[0] == sent.versions[0]


@pytest.mark.req("RF-PR-04")
def test_la_version_nueva_lleva_el_numero_siguiente():
    with pytest.raises(InvalidQuoteError):
        quote(QuoteStatus.SENT).revise(version(1))


@pytest.mark.req("RF-FA-12")
@pytest.mark.parametrize(
    "status", [QuoteStatus.ACCEPTED, QuoteStatus.INVOICED, QuoteStatus.REJECTED]
)
def test_un_aceptado_no_se_edita(status):
    with pytest.raises(QuoteNotEditableError):
        quote(status).revise(version(1))


@pytest.mark.req("RN-06")
def test_no_se_envia_con_lineas_sin_precio():
    unpriced = quote(QuoteStatus.DRAFT, version(1, quote_line(None)))
    assert not unpriced.current_version.is_fully_priced
    with pytest.raises(InvalidQuoteError):
        unpriced.send()
    with pytest.raises(InvalidQuoteError):
        quote(QuoteStatus.DRAFT, dataclasses.replace(version(), lines=())).send()


@pytest.mark.req("RN-06")
def test_linea_sin_origen_queda_sin_precio():
    unpriced = quote_line(None)
    assert unpriced.priced_base is None
    with pytest.raises(InvalidQuoteError):
        unpriced.to_invoice_line()
    with pytest.raises(InvalidQuoteError):
        quote_line("45.00", price_source=PriceSource.none())
    with pytest.raises(InvalidQuoteError):
        quote_line(None, price_source=PriceSource.manual())


@pytest.mark.req("RN-06")
@pytest.mark.req("RN-07")
@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": PriceSourceKind.CATALOG},
        {"kind": PriceSourceKind.SIMILAR_QUOTE},
        {"kind": PriceSourceKind.MANUAL, "reference_id": uuid4()},
        {"kind": PriceSourceKind.HISTORY_MEDIAN},
        {"kind": PriceSourceKind.HISTORY_MEDIAN, "sample_count": 2},
        {"kind": PriceSourceKind.MANUAL, "sample_count": 5},
    ],
)
def test_origen_del_precio_no_valido(kwargs):
    with pytest.raises(InvalidQuoteError):
        PriceSource(**kwargs)


@pytest.mark.req("RN-06")
@pytest.mark.req("RN-07")
def test_origenes_del_precio_validos():
    assert PriceSource(kind=PriceSourceKind.HISTORY_MEDIAN, sample_count=12).sample_count == 12
    assert PriceSource(kind=PriceSourceKind.CATALOG, reference_id=uuid4())
    assert PriceSource(kind=PriceSourceKind.SIMILAR_QUOTE, reference_id=uuid4())


@pytest.mark.req("RF-FA-03")
def test_la_linea_del_presupuesto_pasa_a_la_factura_citandola():
    source = quote_line("45.00", discount=Percentage.of("10"), is_material=True)
    invoice_line = source.to_invoice_line()
    assert invoice_line.origin is LineOrigin.QUOTE
    assert invoice_line.quote_line_id == source.id
    assert invoice_line.base == source.priced_base == money("121.50")
    assert invoice_line.is_material


@pytest.mark.req("RF-PR-04")
@pytest.mark.parametrize(
    "kwargs",
    [{"description": ""}, {"description": " x"}, {"is_material": True, "outside_works": True}],
)
def test_lineas_de_presupuesto_no_validas(kwargs):
    with pytest.raises(InvalidQuoteError):
        quote_line(**kwargs)


@pytest.mark.req("RN-F-13")
def test_version_necesita_los_datos_del_iva_de_la_obra():
    with pytest.raises(InvalidQuoteError):
        dataclasses.replace(version(), dwelling_over_two_years=None)
    business = dataclasses.replace(
        version(), recipient_type=RecipientType.BUSINESS, dwelling_over_two_years=None
    )
    assert business.dwelling_over_two_years is None


@pytest.mark.req("RF-PR-04")
def test_versiones_no_validas():
    repeated = quote_line()
    with pytest.raises(InvalidQuoteError):
        version(1, repeated, repeated)
    with pytest.raises(InvalidQuoteError):
        version(0)
    with pytest.raises(InvalidQuoteError):
        dataclasses.replace(version(), created_at=datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(InvalidQuoteError):
        quote(QuoteStatus.DRAFT, version(2))
    with pytest.raises(InvalidQuoteError):
        dataclasses.replace(quote(), versions=())


@pytest.mark.req("RN-F-13")
def test_base_presupuestada_con_lineas_con_precio():
    current = version(1, quote_line("45.00"), quote_line(None), quote_line("10.00", "1"))
    assert current.base == money("145.00")


@pytest.mark.req("RN-F-13")
def test_el_40_con_las_lineas_del_presupuesto():
    current = version(
        1,
        quote_line("3000.00", "1"),
        quote_line("1800.00", "1", is_material=True),
        quote_line("600.00", "1", outside_works=True),
        quote_line(None),
    )
    result = material_share(current.lines)
    assert (result.works_base, result.material_base) == (money("4800.00"), money("1800.00"))


@pytest.mark.req("RN-01")
def test_importes_del_presupuesto_por_encima_del_maximo():
    with pytest.raises(InvalidAmountError):
        quote_line("20000000.00", "2")
    big = quote_line("20000000.00", "1")
    other = quote_line("20000000.00", "1")
    with pytest.raises(InvalidAmountError):
        version(1, big, other)


@pytest.mark.req("RN-07")
def test_con_tres_muestras_ya_se_propone_precio():
    source = PriceSource(kind=PriceSourceKind.HISTORY_MEDIAN, sample_count=3)
    assert source.sample_count == 3


@pytest.mark.req("RN-06")
def test_precio_puesto_a_mano():
    assert PriceSource.manual().kind is PriceSourceKind.MANUAL
    assert PriceSource.none().kind is PriceSourceKind.NONE


@pytest.mark.req("RF-PR-04")
def test_descripcion_de_linea_de_presupuesto_de_1000_caracteres():
    assert len(quote_line(description="x" * 1000).description) == 1000
    with pytest.raises(InvalidQuoteError):
        quote_line(description="x" * 1001)


@pytest.mark.req("RF-FA-03")
@pytest.mark.req("RN-F-13")
def test_lo_que_va_fuera_de_la_obra_sigue_fuera_en_la_factura():
    assert quote_line("600.00", outside_works=True).to_invoice_line().outside_works is True
    assert quote_line("600.00").to_invoice_line().outside_works is False


@pytest.mark.req("RF-PR-04")
def test_editar_el_borrador_de_una_segunda_version_conserva_la_primera():
    second = quote(QuoteStatus.SENT).revise(version(2))
    first = second.versions[0]
    edited = second.revise(version(2, quote_line("50.00")))
    assert [v.version for v in edited.versions] == [1, 2]
    assert edited.versions[0] == first
    assert edited.current_version.base == money("150.00")
