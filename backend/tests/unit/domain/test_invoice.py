"""Agregado Invoice: borrador, emisión, inmutabilidad y reglas de la factura."""

import dataclasses
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from kapataz.domain.billing.codes import (
    InvoiceStatus,
    InvoiceType,
    LineOrigin,
    PhaseType,
    RecipientType,
)
from kapataz.domain.billing.errors import (
    InvalidAmountError,
    InvalidDocumentNumberError,
    InvalidInvoiceError,
    InvalidLineItemError,
    InvoiceAlreadyIssuedError,
    IssueDateBeforeLastError,
    MissingIssueDataError,
    NegativeInvoiceBaseError,
)
from kapataz.domain.billing.ids import InvoiceId, QuoteVersionId
from kapataz.domain.billing.invoice import Guarantee, Invoice
from kapataz.domain.billing.line_item import LineItem
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.unit.domain.billing_factories import (
    CUSTOMER,
    GENERAL,
    ISSUER,
    NOW,
    RECIPIENT,
    REDUCED,
    TENANT,
    TODAY,
    draft,
    issue,
    line,
    money,
    quote_version,
)

QUOTE_VERSION = QuoteVersionId(uuid4())


@pytest.fixture
def invoice_emitida() -> Invoice:
    return issue(draft(line("45.00", "3", description="Punto de luz")))


# ----------------------------------------------------------- importes y borrador


@pytest.mark.req("RN-03")
def test_los_importes_salen_de_las_lineas():
    invoice = draft(line("45.00", "3"), line("10.00"))
    assert invoice.totals.base == money("145.00")
    assert invoice.totals.tax == money("30.45")
    assert invoice.totals.total_amount == money("175.45")


@pytest.mark.req("RF-FA-01")
def test_el_borrador_se_edita_y_cada_cambio_devuelve_otra_factura():
    invoice = draft()
    edited = (
        invoice.add_line(line("100.00"))
        .with_description("Reforma de cocina")
        .with_treatment(VatTreatment.reverse_charge())
        .with_withholding(Percentage.of("15"))
        .with_guarantee(Guarantee(rate=Percentage.of("5"), due_date=TODAY + timedelta(days=365)))
        .with_dates(operation_date=TODAY, due_date=TODAY + timedelta(days=30))
    )
    assert invoice.lines == ()
    assert edited.totals.base == money("100.00")
    assert edited.totals.tax == money("0.00")
    assert edited.totals.withholding == money("15.00")
    assert edited.totals.guarantee == money("5.00")
    assert edited.with_lines([]).lines == ()


@pytest.mark.req("RF-FA-02")
@pytest.mark.req("RN-F-06")
def test_el_numero_se_asigna_al_emitir(invoice_emitida):
    assert draft().number is None
    assert invoice_emitida.status is InvoiceStatus.ISSUED
    assert str(invoice_emitida.number) == "F-2026-0001"
    assert invoice_emitida.issuer == ISSUER
    assert invoice_emitida.recipient == RECIPIENT
    assert invoice_emitida.issued_at == NOW


# ----------------------------------------------------------- inmutabilidad


@pytest.mark.req("RN-F-02")
def test_factura_emitida_no_admite_cambios_en_lineas(invoice_emitida):
    with pytest.raises(InvoiceAlreadyIssuedError):
        invoice_emitida.add_line(line("45.00", description="Punto de luz"))


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RF-FA-04")
@pytest.mark.parametrize(
    "change",
    [
        lambda i: i.with_lines([]),
        lambda i: i.with_description("Otra"),
        lambda i: i.with_treatment(GENERAL),
        lambda i: i.with_withholding(None),
        lambda i: i.with_guarantee(None),
        lambda i: i.with_dates(operation_date=None, due_date=None),
    ],
)
def test_factura_emitida_no_se_modifica(invoice_emitida, change):
    with pytest.raises(InvoiceAlreadyIssuedError) as error:
        change(invoice_emitida)
    assert error.value.slug == "factura-emitida-inmutable"


@pytest.mark.req("RN-F-02")
def test_factura_emitida_no_se_emite_dos_veces(invoice_emitida):
    with pytest.raises(InvoiceAlreadyIssuedError):
        issue(invoice_emitida, sequence=2)


@pytest.mark.req("RN-F-02")
def test_la_entidad_es_inmutable(invoice_emitida):
    with pytest.raises(dataclasses.FrozenInstanceError):
        invoice_emitida.description = "Otra"  # type: ignore[misc]


# ----------------------------------------------------------- datos obligatorios


@pytest.mark.req("RN-F-06")
def test_sin_descripcion_ni_lineas_no_se_emite():
    with pytest.raises(MissingIssueDataError) as error:
        issue(draft(description=None))
    assert error.value.missing == ("description", "lines")


@pytest.mark.req("RN-F-06")
@pytest.mark.req("RN-F-13")
def test_sin_presupuesto_hay_que_saber_destinatario_y_vivienda():
    assert draft(line("1.00"), recipient_type=None).missing_issue_data() == ("recipient_type",)
    private = draft(line("1.00"), treatment=GENERAL, recipient_type=RecipientType.PRIVATE)
    assert private.missing_issue_data() == ("dwelling_over_two_years",)
    business = draft(line("1.00"), recipient_type=RecipientType.BUSINESS)
    assert business.missing_issue_data() == ()
    from_quote = draft(line("1.00"), quote_version_id=QUOTE_VERSION)
    assert from_quote.missing_issue_data() == ()


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("description", ["", " x", "x" * 501])
def test_descripcion_general_no_valida(description):
    with pytest.raises(InvalidInvoiceError):
        draft(description=description)


@pytest.mark.req("RN-F-06")
def test_descripcion_general_de_500_caracteres():
    assert draft(description="x" * 500).description == "x" * 500


# ----------------------------------------------------------- emisión


@pytest.mark.req("RN-F-04")
def test_fecha_anterior_a_la_ultima_de_la_serie():
    with pytest.raises(IssueDateBeforeLastError):
        draft(line("1.00")).issue(
            number=DocumentNumber(Series.invoices(), 2026, 2),
            issue_date=date(2026, 3, 1),
            issued_at=NOW,
            issuer=ISSUER,
            recipient=RECIPIENT,
            last_issue_date=date(2026, 3, 2),
        )


@pytest.mark.req("RN-F-01")
@pytest.mark.parametrize(
    "number",
    [DocumentNumber(Series.correctives(), 2026, 1), DocumentNumber(Series.invoices(), 2025, 1)],
)
def test_el_numero_es_de_la_serie_y_el_anio_de_la_factura(number):
    with pytest.raises(InvalidDocumentNumberError):
        draft(line("1.00")).issue(
            number=number,
            issue_date=TODAY,
            issued_at=NOW,
            issuer=ISSUER,
            recipient=RECIPIENT,
            last_issue_date=None,
        )


@pytest.mark.req("RN-F-12")
def test_no_se_emite_una_factura_con_base_negativa():
    with pytest.raises(NegativeInvoiceBaseError):
        issue(draft(line("100.00"), line("-200.00")))


@pytest.mark.req("RF-FA-14")
def test_el_vencimiento_no_es_anterior_a_la_expedicion():
    invoice = draft(line("1.00")).with_dates(operation_date=None, due_date=TODAY - timedelta(1))
    with pytest.raises(InvalidInvoiceError):
        issue(invoice)


@pytest.mark.req("RF-FA-15")
def test_el_vencimiento_de_la_garantia_no_es_anterior_a_la_expedicion():
    invoice = draft(line("1.00")).with_guarantee(
        Guarantee(rate=Percentage.of("5"), due_date=TODAY - timedelta(1))
    )
    with pytest.raises(InvalidInvoiceError):
        issue(invoice)


@pytest.mark.req("RN-F-02")
def test_estados_imposibles(invoice_emitida):
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(draft(), number=DocumentNumber(Series.invoices(), 2026, 1))
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(invoice_emitida, issuer=None)
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(invoice_emitida, issued_at=datetime(2026, 1, 1))  # noqa: DTZ001
    with pytest.raises(InvalidDocumentNumberError):
        dataclasses.replace(invoice_emitida, series=Series.correctives())
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(draft(), created_at=datetime(2026, 1, 1))  # noqa: DTZ001


# ----------------------------------------------------------- tipo y fases


@pytest.mark.req("RF-FA-04")
@pytest.mark.parametrize("invoice_type", [InvoiceType.F2, InvoiceType.R1])
def test_una_factura_es_completa_f1(invoice_type):
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(draft(), invoice_type=invoice_type)


@pytest.mark.req("RF-FA-10")
def test_las_fases_salen_de_un_presupuesto():
    with pytest.raises(InvalidInvoiceError):
        draft(line("1.00"), phase_type=PhaseType.PROGRESS)
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(draft(), phase_type=None)
    progress = draft(line("1.00"), phase_type=PhaseType.PROGRESS, quote_version_id=QUOTE_VERSION)
    assert progress.phase_type is PhaseType.PROGRESS


@pytest.mark.req("RF-FA-15")
@pytest.mark.parametrize("phase", [PhaseType.PROGRESS])
def test_la_garantia_solo_en_completa_o_final(phase):
    guarantee = Guarantee(rate=Percentage.of("5"), due_date=TODAY)
    invoice = draft(line("1.00"), phase_type=phase, quote_version_id=QUOTE_VERSION)
    with pytest.raises(InvalidInvoiceError):
        invoice.with_guarantee(guarantee)
    final = draft(line("1.00"), phase_type=PhaseType.FINAL, quote_version_id=QUOTE_VERSION)
    assert final.with_guarantee(guarantee).guarantee == guarantee


@pytest.mark.req("RF-FA-15")
@pytest.mark.parametrize("rate", ["0", "100"])
def test_garantia_fuera_de_rango(rate):
    with pytest.raises(InvalidInvoiceError):
        Guarantee(rate=Percentage.of(rate), due_date=TODAY)


@pytest.mark.req("RF-FA-05")
@pytest.mark.parametrize("rate", ["0", "100"])
def test_retencion_fuera_de_rango(rate):
    with pytest.raises(InvalidInvoiceError):
        draft().with_withholding(Percentage.of(rate))


@pytest.mark.req("RN-F-12")
def test_solo_la_final_resta_facturas_anteriores():
    prior = LineItem(
        description="A deducir",
        quantity=Quantity.one(),
        unit_price=money("-100.00"),
        origin=LineOrigin.PRIOR_INVOICE,
        prior_invoice_id=InvoiceId(uuid4()),
    )
    with pytest.raises(InvalidInvoiceError):
        draft(prior, phase_type=PhaseType.PROGRESS, quote_version_id=QUOTE_VERSION)
    final = draft(
        line("300.00", origin=LineOrigin.QUOTE),
        prior,
        phase_type=PhaseType.FINAL,
        quote_version_id=QUOTE_VERSION,
    )
    assert final.totals.base == money("200.00")


@pytest.mark.req("RF-FA-12")
def test_trabajo_adicional_marcado_en_la_app():
    baths = line("3000.00", origin=LineOrigin.ADDITIONAL, description="Baños")
    invoice = draft(line("6000.00", origin=LineOrigin.QUOTE), baths, quote_version_id=QUOTE_VERSION)
    assert invoice.additional_work == (baths,)
    assert invoice.totals.base == money("9000.00")


@pytest.mark.req("RF-FA-12")
def test_sin_presupuesto_las_lineas_no_tienen_origen():
    with pytest.raises(InvalidInvoiceError):
        draft(line("1.00", origin=LineOrigin.ADDITIONAL))


@pytest.mark.req("RN-F-13")
def test_con_presupuesto_destinatario_y_vivienda_estan_en_el():
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(
            draft(quote_version_id=QUOTE_VERSION), recipient_type=RecipientType.PRIVATE
        )


# ----------------------------------------------------------- desde un presupuesto


def from_quote(treatment: VatTreatment, phase: PhaseType = PhaseType.FULL) -> Invoice:
    """Borrador que sale de ``QUOTE_VERSION``: sin destinatario ni vivienda propios."""
    if phase is PhaseType.ADVANCE:
        return advance("1100.00", treatment)
    return draft(
        line("1000.00", origin=LineOrigin.QUOTE),
        treatment=treatment,
        phase_type=phase,
        quote_version_id=QUOTE_VERSION,
    )


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("phase", [PhaseType.FULL, PhaseType.ADVANCE, PhaseType.PROGRESS])
@pytest.mark.parametrize(
    ("recipient", "dwelling"),
    [
        (RecipientType.BUSINESS, None),
        (RecipientType.BUSINESS, True),
        (RecipientType.PRIVATE, False),
        (RecipientType.COMMUNITY, False),
    ],
)
def test_desde_presupuesto_no_se_emite_al_10_sin_destinatario_y_vivienda_que_lo_admitan(
    phase, recipient, dwelling
):
    # El borrador no lo sabe todavía; la emisión lo comprueba con la versión.
    invoice = from_quote(REDUCED, phase)
    version = quote_version(
        QUOTE_VERSION, recipient_type=recipient, dwelling_over_two_years=dwelling
    )

    with pytest.raises(InvalidInvoiceError, match="10 %"):
        issue(invoice, version=version)


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RF-FA-05")
@pytest.mark.parametrize("recipient", [RecipientType.PRIVATE, RecipientType.COMMUNITY])
def test_desde_presupuesto_no_se_invierte_el_sujeto_pasivo_a_un_particular(recipient):
    invoice = from_quote(VatTreatment.reverse_charge())
    version = quote_version(QUOTE_VERSION, recipient_type=recipient)

    with pytest.raises(InvalidInvoiceError, match="inversión"):
        issue(invoice, version=version)


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RF-FA-03")
@pytest.mark.parametrize(
    ("treatment", "recipient", "dwelling"),
    [
        (REDUCED, RecipientType.PRIVATE, True),
        (REDUCED, RecipientType.COMMUNITY, True),
        (GENERAL, RecipientType.PRIVATE, False),
        (VatTreatment.reverse_charge(), RecipientType.BUSINESS, None),
    ],
)
def test_al_emitir_copia_destinatario_y_vivienda_de_la_version(treatment, recipient, dwelling):
    invoice = from_quote(treatment)
    version = quote_version(
        QUOTE_VERSION, recipient_type=recipient, dwelling_over_two_years=dwelling
    )

    issued = issue(invoice, version=version)

    assert issued.is_issued
    assert (issued.recipient_type, issued.dwelling_over_two_years) == (recipient, dwelling)
    assert issued.quote_version_id == QUOTE_VERSION
    # El borrador no cambia: sigue sin duplicar lo que está en el presupuesto.
    assert (invoice.recipient_type, invoice.dwelling_over_two_years) == (None, None)


@pytest.mark.req("RN-F-13")
def test_se_emite_con_la_version_de_la_que_sale_y_solo_con_ella():
    invoice = from_quote(REDUCED)
    other = quote_version(QuoteVersionId(uuid4()))

    with pytest.raises(InvalidInvoiceError, match="versión del presupuesto"):
        invoice.issue(
            number=DocumentNumber(Series.invoices(), 2026, 1),
            issue_date=TODAY,
            issued_at=NOW,
            issuer=ISSUER,
            recipient=RECIPIENT,
            last_issue_date=None,
        )
    with pytest.raises(InvalidInvoiceError, match="versión del presupuesto"):
        issue(invoice, version=other)
    # Una factura sin presupuesto no toma los datos de uno ajeno.
    with pytest.raises(InvalidInvoiceError, match="no sale de un presupuesto"):
        issue(draft(line("1.00")), version=other)


@pytest.mark.req("RN-F-13")
def test_sin_presupuesto_la_emitida_conserva_sus_propios_datos():
    invoice = draft(
        line("1000.00"),
        treatment=REDUCED,
        recipient_type=RecipientType.COMMUNITY,
        dwelling_over_two_years=True,
    )

    issued = issue(invoice)

    assert (issued.recipient_type, issued.dwelling_over_two_years) == (
        RecipientType.COMMUNITY,
        True,
    )


# ----------------------------------------------------------- IVA de la obra


@pytest.mark.req("RN-F-13")
def test_lo_que_no_es_obra_solo_va_al_21():
    appliance = line("600.00", outside_works=True)
    assert draft(appliance, treatment=GENERAL).totals.tax == money("126.00")
    with pytest.raises(InvalidInvoiceError):
        draft(
            appliance,
            treatment=REDUCED,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    ("recipient", "dwelling"),
    [
        (RecipientType.BUSINESS, None),
        (RecipientType.PRIVATE, False),
        (RecipientType.COMMUNITY, False),
    ],
)
def test_el_10_exige_particular_o_comunidad_y_vivienda_de_dos_anios(recipient, dwelling):
    with pytest.raises(InvalidInvoiceError):
        draft(
            line("1.00"),
            treatment=REDUCED,
            recipient_type=recipient,
            dwelling_over_two_years=dwelling,
        )


@pytest.mark.req("RN-F-13")
def test_el_10_con_particular_y_vivienda_antigua():
    invoice = draft(
        line("1000.00"),
        treatment=REDUCED,
        recipient_type=RecipientType.PRIVATE,
        dwelling_over_two_years=True,
    )
    assert invoice.totals.tax == money("100.00")


@pytest.mark.req("RN-F-05")
def test_inversion_solo_con_empresario():
    with pytest.raises(InvalidInvoiceError):
        draft(
            line("1.00"),
            treatment=VatTreatment.reverse_charge(),
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    invoice = draft(line("1000.00"), treatment=VatTreatment.reverse_charge())
    assert invoice.totals.tax == money("0.00")
    assert invoice.treatment.mention == "Inversión del sujeto pasivo"


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize("phase", [PhaseType.FULL, PhaseType.FINAL])
def test_al_10_el_material_no_supera_el_40_en_la_obra_entera(phase):
    lines = (
        line("2500.00", origin=LineOrigin.QUOTE),
        line("2500.00", is_material=True, origin=LineOrigin.QUOTE),
    )
    with pytest.raises(InvalidInvoiceError):
        draft(*lines, treatment=REDUCED, phase_type=phase, quote_version_id=QUOTE_VERSION)
    assert draft(*lines, treatment=GENERAL, phase_type=phase, quote_version_id=QUOTE_VERSION)


@pytest.mark.req("RN-F-13")
def test_la_certificacion_no_comprueba_el_40_con_una_parte_de_la_obra():
    invoice = draft(
        line("2500.00", is_material=True, origin=LineOrigin.QUOTE),
        treatment=REDUCED,
        phase_type=PhaseType.PROGRESS,
        quote_version_id=QUOTE_VERSION,
    )
    assert invoice.totals.base == money("2500.00")


@pytest.mark.req("RN-F-13")
def test_una_factura_lleva_un_solo_tipo_de_iva():
    field_names = {field.name for field in dataclasses.fields(Invoice)}
    assert "treatment" in field_names
    assert not {"tax_rate", "rate"} & {field.name for field in dataclasses.fields(LineItem)}


# ----------------------------------------------------------- anticipo


def advance(gross: str, treatment: VatTreatment = REDUCED, **kwargs: object) -> Invoice:
    return Invoice.advance(
        id=InvoiceId(uuid4()),
        tenant_id=TENANT,
        customer_id=CUSTOMER,
        quote_version_id=QUOTE_VERSION,
        series=Series.invoices(),
        treatment=treatment,
        gross_amount=money(gross),
        line_description="Anticipo de la reforma",
        created_at=NOW,
        description="Anticipo",
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.req("RN-F-12")
@pytest.mark.req("RF-FA-10")
def test_anticipo_antes_de_empezar_la_obra():
    invoice = issue(advance("6000.00"))
    assert invoice.phase_type is PhaseType.ADVANCE
    assert invoice.totals.base == money("5454.55")
    assert invoice.totals.tax == money("545.45")
    assert invoice.totals.total_amount == money("6000.00")
    assert invoice.lines[0].base == money("5454.55")


@pytest.mark.req("RN-F-12")
def test_anticipo_con_retencion():
    invoice = advance("1210.00", GENERAL, withholding_rate=Percentage.of("15"))
    assert invoice.totals.withholding == money("150.00")
    assert invoice.totals.amount_due == money("1060.00")


@pytest.mark.req("RN-F-12")
def test_anticipo_no_valido():
    good = advance("6000.00")
    with pytest.raises(InvalidInvoiceError):
        advance("0.00")
    with pytest.raises(InvalidInvoiceError):
        good.add_line(line("1.00"))
    with pytest.raises(InvalidInvoiceError):
        good.with_lines([line("5454.56")])
    with pytest.raises(InvalidInvoiceError):
        good.with_lines([line("5454.55", is_material=True)])
    with pytest.raises(InvalidInvoiceError):
        good.with_guarantee(Guarantee(rate=Percentage.of("5"), due_date=TODAY))
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(good, phase_type=PhaseType.PROGRESS)
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(draft(line("1.00")), gross_amount=money("1.00"))


@pytest.mark.req("RN-F-13")
def test_anticipo_al_tipo_de_la_obra():
    assert advance("6000.00", REDUCED).treatment.rate == TaxRate.reduced()


# ----------------------------------------------------------- líneas


@pytest.mark.req("RF-FA-12")
@pytest.mark.parametrize(
    "kwargs",
    [
        {"description": ""},
        {"description": " x"},
        {"description": "x" * 1001},
        {"is_material": True, "outside_works": True},
        {"origin": LineOrigin.QUOTE},
        {"quote_line_id": uuid4()},
        {"origin": LineOrigin.PRIOR_INVOICE},
        {"prior_invoice_id": uuid4()},
        {"origin": LineOrigin.PRIOR_INVOICE, "prior_invoice_id": uuid4()},
        {
            "origin": LineOrigin.PRIOR_INVOICE,
            "prior_invoice_id": uuid4(),
            "unit_price": money("-1.00"),
            "quantity": Quantity.of(2),
        },
        {
            "origin": LineOrigin.PRIOR_INVOICE,
            "prior_invoice_id": uuid4(),
            "unit_price": money("-1.00"),
            "discount": Percentage.of(5),
        },
        {
            "origin": LineOrigin.PRIOR_INVOICE,
            "prior_invoice_id": uuid4(),
            "unit_price": money("-1.00"),
            "is_material": True,
        },
        {
            "origin": LineOrigin.PRIOR_INVOICE,
            "prior_invoice_id": uuid4(),
            "unit_price": money("-1.00"),
            "outside_works": True,
        },
    ],
)
def test_lineas_no_validas(kwargs):
    values = {
        "description": "Trabajo",
        "quantity": Quantity.one(),
        "unit_price": money("1.00"),
    } | kwargs
    with pytest.raises(InvalidLineItemError):
        LineItem(**values)


@pytest.mark.req("RN-F-12")
def test_la_resta_de_una_factura_no_cuenta_para_la_obra():
    prior = LineItem(
        description="A deducir",
        quantity=Quantity.one(),
        unit_price=money("-100.00"),
        origin=LineOrigin.PRIOR_INVOICE,
        prior_invoice_id=InvoiceId(uuid4()),
    )
    assert not prior.counts_for_works
    assert prior.priced_base == money("-100.00")
    assert line("1.00").counts_for_works
    assert not line("1.00", outside_works=True).counts_for_works


# ----------------------------------------------------------- domicilios


def _issue_with(issuer, recipient):
    return draft(line("1.00")).issue(
        number=DocumentNumber(Series.invoices(), 2026, 1),
        issue_date=TODAY,
        issued_at=NOW,
        issuer=issuer,
        recipient=recipient,
        last_issue_date=None,
    )


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize(
    ("issuer_address", "recipient_address", "missing"),
    [
        (None, "Calle Mayor 1", ("issuer_address",)),
        ("Calle Mayor 1", None, ("recipient_address",)),
        (None, None, ("issuer_address", "recipient_address")),
    ],
)
def test_sin_domicilio_no_se_emite(issuer_address, recipient_address, missing):
    issuer = dataclasses.replace(ISSUER, address=issuer_address)
    recipient = dataclasses.replace(RECIPIENT, address=recipient_address)
    with pytest.raises(MissingIssueDataError) as error:
        _issue_with(issuer, recipient)
    assert error.value.missing == missing


@pytest.mark.req("RN-F-06")
@pytest.mark.req("RN-F-02")
def test_la_emitida_guarda_la_copia_completa_de_las_partes(invoice_emitida):
    assert invoice_emitida.issuer.address == "Calle Mayor 1, 28001 Madrid"
    assert invoice_emitida.recipient.address == "Avenida del Puerto 2, 46021 Valencia"
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(invoice_emitida, recipient=dataclasses.replace(RECIPIENT, address=None))


# ----------------------------------------------------------- tope de importes


@pytest.mark.req("RN-01")
def test_un_total_por_encima_del_maximo_se_rechaza_al_crear_el_borrador():
    # 20.000.000 € de base caben en Money, pero el total con el 21 % no.
    with pytest.raises(InvalidAmountError):
        draft(line("20000000.00"))
    with pytest.raises(InvalidAmountError):
        draft(line("1.00")).with_lines([line("20000000.00")])
    with pytest.raises(InvalidAmountError):
        draft(line("1.00")).add_line(line("20000000.00"))


@pytest.mark.req("RN-01")
def test_una_suma_de_lineas_por_encima_del_maximo_se_rechaza():
    with pytest.raises(InvalidAmountError):
        draft(line("15000000.00"), line("15000000.00"), treatment=VatTreatment.reverse_charge())
    with pytest.raises(InvalidAmountError):
        line("20000000.00", "2")


@pytest.mark.req("RN-F-05")
def test_con_inversion_cabe_la_base_que_al_21_no_cabria():
    invoice = draft(line("20000000.00"), treatment=VatTreatment.reverse_charge())
    assert invoice.totals.total_amount == money("20000000.00")
