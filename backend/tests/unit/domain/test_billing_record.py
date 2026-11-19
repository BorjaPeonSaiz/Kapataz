"""Registros de facturación: contenido canónico, huella y cadena única (RN-F-07, RF-VF-01)."""

import dataclasses
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.billing_record import (
    CANCELLATION_REQUIRED_FIELDS,
    REGISTRATION_REQUIRED_FIELDS,
    BillingRecord,
    ChainLink,
    RecordType,
    SubmissionStatus,
    SystemInfo,
    cancellation_hash_input,
    cancellation_record,
    canonical_json,
    compute_record_hash,
    is_cancelled,
    registration_hash_input,
    registration_record,
    sha256_hash,
    verify_chain,
)
from kapataz.domain.billing.codes import CorrectionType, InvoiceType
from kapataz.domain.billing.errors import InvalidBillingRecordError
from kapataz.domain.billing.ids import BillingRecordId, InvoiceId
from kapataz.domain.billing.invoice import Invoice, RectifiedInvoice
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage
from kapataz.domain.billing.tax import VatTreatment
from kapataz.domain.customers.tax_id import TaxId
from tests.unit.domain.billing_factories import (
    NOW,
    SYSTEM,
    TODAY,
    corrective,
    draft,
    issue,
    line,
    money,
)


def alta(
    invoice: Invoice, previous: BillingRecord | None = None, **kwargs: object
) -> BillingRecord:
    return registration_record(
        record_id=BillingRecordId(uuid4()),
        invoice=invoice,
        previous=previous,
        system=SYSTEM,
        generated_at=kwargs.pop("generated_at", NOW),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def anulacion(
    invoice: Invoice, previous: BillingRecord | None, external_ref: str | None = None
) -> BillingRecord:
    return cancellation_record(
        record_id=BillingRecordId(uuid4()),
        invoice=invoice,
        previous=previous,
        system=SYSTEM,
        generated_at=NOW,
        external_ref=external_ref,
    )


@pytest.fixture
def invoice() -> Invoice:
    return issue(draft(line("1000.00"), description="Reforma de baño"))


@pytest.mark.req("RN-F-07")
@pytest.mark.req("RF-VF-01")
def test_cada_campo_obligatorio_del_alta_tiene_su_dato(invoice):
    content = alta(invoice).content()
    for name in REGISTRATION_REQUIRED_FIELDS:
        assert content.get(name) not in (None, "", [], {}), name
    assert content["IDFactura"] == {
        "IDEmisorFactura": "12345678Z",
        "NumSerieFactura": "F-2026-0001",
        "FechaExpedicionFactura": "18-11-2026",
    }
    assert content["TipoFactura"] == "F1"
    assert content["NombreRazonEmisor"] == "Reformas Ejemplo"
    assert content["Destinatarios"] == [{"NombreRazon": "Cliente Ejemplo", "NIF": "B12345674"}]
    assert content["Desglose"] == [
        {
            "Impuesto": "01",
            "ClaveRegimen": "01",
            "CalificacionOperacion": "S1",
            "TipoImpositivo": "21.00",
            "BaseImponibleOimporteNoSujeto": "1000.00",
            "CuotaRepercutida": "210.00",
        }
    ]
    assert content["CuotaTotal"] == "210.00"
    assert content["ImporteTotal"] == "1210.00"
    assert content["Encadenamiento"] == {"PrimerRegistro": "S"}
    assert content["FechaHoraHusoGenRegistro"] == "2026-11-18T09:30:00+00:00"
    assert content["TipoHuella"] == "01"
    assert content["Subsanacion"] == "N"
    assert content["RechazoPrevio"] == "N"
    assert content["SistemaInformatico"] == {
        "NombreRazon": "KodigoLab",
        "NIF": "A58818501",
        "NombreSistemaInformatico": "Kapataz",
        "IdSistemaInformatico": "KZ",
        "Version": "0123abc",
        "NumeroInstalacion": "local-1",
        "TipoUsoPosibleSoloVerifactu": "S",
        "TipoUsoPosibleMultiOT": "S",
        "IndicadorMultiplesOT": "S",
    }


@pytest.mark.req("RN-F-07")
def test_cada_campo_obligatorio_de_la_anulacion_tiene_su_dato(invoice):
    record = anulacion(invoice, alta(invoice))
    content = record.content()
    for name in CANCELLATION_REQUIRED_FIELDS:
        assert content.get(name) not in (None, "", [], {}), name
    assert content["IDFactura"] == {
        "IDEmisorFacturaAnulada": "12345678Z",
        "NumSerieFacturaAnulada": "F-2026-0001",
        "FechaExpedicionFacturaAnulada": "18-11-2026",
    }
    assert record.record_type is RecordType.CANCELLATION
    assert "RegistroAnterior" in content["Encadenamiento"]
    assert anulacion(invoice, None, external_ref="REF-2").content()["RefExterna"] == "REF-2"


@pytest.mark.req("RN-F-07")
def test_importe_total_sin_retencion_ni_garantia():
    with_withholding = issue(draft(line("1000.00")).with_withholding(Percentage.of("15")))
    content = alta(with_withholding).content()
    assert content["ImporteTotal"] == "1210.00"
    assert with_withholding.totals.amount_due.amount < with_withholding.totals.total_amount.amount


@pytest.mark.req("RN-F-07")
@pytest.mark.req("RN-F-05")
def test_desglose_con_inversion_del_sujeto_pasivo():
    reverse = issue(draft(line("1000.00"), treatment=VatTreatment.reverse_charge()))
    (detail,) = alta(reverse).content()["Desglose"]
    assert detail["CalificacionOperacion"] == "S2"
    assert detail["TipoImpositivo"] == "0.00"
    assert detail["CuotaRepercutida"] == "0.00"


@pytest.mark.req("RN-F-07")
@pytest.mark.req("RN-F-03")
def test_rectificativa_lleva_tipo_y_facturas_rectificadas():
    first = RectifiedInvoice(
        invoice_id=InvoiceId(uuid4()),
        number=DocumentNumber.parse("F-2026-0001"),
        issue_date=date(2026, 3, 1),
        rectified_base=None,
        rectified_tax=None,
    )
    difference = issue(corrective(line("-100.00"), rectified=(first,)))
    content = alta(difference).content()
    assert content["TipoFactura"] == "R1"
    assert content["TipoRectificativa"] == "I"
    assert content["FacturasRectificadas"] == [
        {
            "IDEmisorFactura": "12345678Z",
            "NumSerieFactura": "F-2026-0001",
            "FechaExpedicionFactura": "01-03-2026",
        }
    ]
    assert "ImporteRectificacion" not in content
    substitution = issue(
        corrective(
            line("900.00"),
            rectified=(
                dataclasses.replace(
                    first, rectified_base=money("1000"), rectified_tax=money("210")
                ),
            ),
            correction_type=CorrectionType.SUBSTITUTION,
            invoice_type=InvoiceType.R4,
        )
    )
    content = alta(substitution).content()
    assert content["TipoRectificativa"] == "S"
    assert content["ImporteRectificacion"] == {
        "BaseRectificada": "1000.00",
        "CuotaRectificada": "210.00",
    }


@pytest.mark.req("RN-F-07")
def test_fecha_de_operacion_y_referencia_externa():
    invoice = issue(
        draft(line("1.00")).with_dates(operation_date=TODAY - timedelta(days=3), due_date=None)
    )
    content = alta(invoice, external_ref="REF-1").content()
    assert content["FechaOperacion"] == "15-11-2026"
    assert content["RefExterna"] == "REF-1"
    same_day = issue(draft(line("1.00")).with_dates(operation_date=TODAY, due_date=None))
    assert "FechaOperacion" not in alta(same_day).content()


# Ejemplos de §6 de «Detalle de las especificaciones técnicas para generación
# de la huella o hash de los registros de facturación» (AEAT, v0.1.2).
CASE_1 = "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"
CASE_2 = "F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97"
CASE_3 = "177547C0D57AC74748561D054A9CEC14B4C4EA23D1BEFD6F2E69E3A388F90C68"


@pytest.mark.req("RN-F-07")
def test_huella_oficial_caso_1_alta_primer_registro():
    hash_input = registration_hash_input(
        issuer_tax_id="89890001K",
        series_number="12345678/G33",
        issue_date="01-01-2024",
        invoice_type="F1",
        tax_total="12.35",
        total_amount="123.45",
        previous_hash="",
        generated_at="2024-01-01T19:20:30+01:00",
    )
    assert hash_input == (
        "IDEmisorFactura=89890001K&NumSerieFactura=12345678/G33&FechaExpedicionFactura="
        "01-01-2024&TipoFactura=F1&CuotaTotal=12.35&ImporteTotal=123.45&Huella="
        "&FechaHoraHusoGenRegistro=2024-01-01T19:20:30+01:00"
    )
    assert sha256_hash(hash_input) == CASE_1


@pytest.mark.req("RN-F-07")
def test_huella_oficial_caso_2_alta_encadenada():
    hash_input = registration_hash_input(
        issuer_tax_id="89890001K",
        series_number="12345679/G34",
        issue_date="01-01-2024",
        invoice_type="F1",
        tax_total="12.35",
        total_amount="123.45",
        previous_hash=CASE_1,
        generated_at="2024-01-01T19:20:35+01:00",
    )
    assert sha256_hash(hash_input) == CASE_2


@pytest.mark.req("RN-F-07")
def test_huella_oficial_caso_3_anulacion():
    hash_input = cancellation_hash_input(
        issuer_tax_id="89890001K",
        series_number="12345679/G34",
        issue_date="01-01-2024",
        previous_hash=CASE_2,
        generated_at="2024-01-01T19:20:40+01:00",
    )
    assert hash_input == (
        "IDEmisorFacturaAnulada=89890001K&NumSerieFacturaAnulada=12345679/G34"
        "&FechaExpedicionFacturaAnulada=01-01-2024&Huella=" + CASE_2 + "&"
        "FechaHoraHusoGenRegistro=2024-01-01T19:20:40+01:00"
    )
    assert sha256_hash(hash_input) == CASE_3


@pytest.mark.req("RN-F-07")
def test_los_valores_de_la_huella_van_sin_espacios_en_los_bordes():
    padded = cancellation_hash_input(
        issuer_tax_id=" 89890001K ",
        series_number="12345679/G34 ",
        issue_date=" 01-01-2024",
        previous_hash=CASE_2,
        generated_at="2024-01-01T19:20:40+01:00 ",
    )
    assert sha256_hash(padded) == CASE_3


def _official(previous_hash: str, record_type: RecordType = RecordType.REGISTRATION) -> str:
    if record_type is RecordType.CANCELLATION:
        hash_input = cancellation_hash_input(
            issuer_tax_id="12345678Z",
            series_number="F-2026-0001",
            issue_date="18-11-2026",
            previous_hash=previous_hash,
            generated_at="2026-11-18T09:30:00+00:00",
        )
    else:
        hash_input = registration_hash_input(
            issuer_tax_id="12345678Z",
            series_number="F-2026-0001",
            issue_date="18-11-2026",
            invoice_type="F1",
            tax_total="210.00",
            total_amount="1210.00",
            previous_hash=previous_hash,
            generated_at="2026-11-18T09:30:00+00:00",
        )
    return sha256_hash(hash_input)


@pytest.mark.req("RN-F-07")
def test_huella_del_registro_con_el_algoritmo_oficial(invoice):
    record = alta(invoice)
    assert record.hash == _official("")
    assert record.hash == compute_record_hash(RecordType.REGISTRATION, record.content())
    assert len(record.hash) == 64
    assert record.canonical_json == canonical_json(json.loads(record.canonical_json))
    assert record.is_first
    second = alta(invoice, record)
    assert second.hash == _official(record.hash)
    cancel = anulacion(invoice, second)
    assert cancel.hash == _official(second.hash, RecordType.CANCELLATION)


@pytest.mark.req("RN-F-07")
def test_contenido_sin_los_campos_de_la_huella():
    with pytest.raises(InvalidBillingRecordError):
        compute_record_hash(RecordType.REGISTRATION, {"Encadenamiento": {"PrimerRegistro": "S"}})
    with pytest.raises(InvalidBillingRecordError):
        compute_record_hash(RecordType.CANCELLATION, {"Encadenamiento": "S"})
    with pytest.raises(InvalidBillingRecordError):
        compute_record_hash(
            RecordType.CANCELLATION,
            {"Encadenamiento": {"PrimerRegistro": "S"}, "IDFactura": {}},
        )


@pytest.mark.req("RN-F-07")
def test_un_registro_alterado_no_se_puede_cargar(invoice):
    record = alta(invoice)
    # ImporteTotal entra en la huella oficial; cambiarlo sin recalcularla se nota.
    tampered = record.canonical_json.replace('"ImporteTotal":"1210.00"', '"ImporteTotal":"1200.00"')
    assert tampered != record.canonical_json
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, canonical_json=tampered)
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, previous=record.as_link())


@pytest.mark.req("RN-F-07")
def test_subsanacion_y_anulacion_se_encadenan_en_la_misma_cadena_que_las_altas():
    first_invoice = issue(draft(line("100.00")))
    corrective_series = issue(
        corrective(
            line("-10.00"),
            rectified=(
                RectifiedInvoice(
                    invoice_id=first_invoice.id,
                    number=DocumentNumber.parse("F-2026-0001"),
                    issue_date=TODAY,
                ),
            ),
        )
    )
    first = alta(first_invoice)
    second = alta(corrective_series, first)
    fix = alta(first_invoice, second, is_correction=True, prior_rejection=True)
    cancel = anulacion(first_invoice, fix)
    chain = [first, second, fix, cancel]
    verify_chain(chain)
    assert [r.record_type for r in chain] == [
        RecordType.REGISTRATION,
        RecordType.REGISTRATION,
        RecordType.REGISTRATION,
        RecordType.CANCELLATION,
    ]
    assert second.previous == first.as_link()
    assert second.content()["Encadenamiento"]["RegistroAnterior"]["Huella"] == first.hash
    assert fix.content()["Subsanacion"] == "S"
    assert fix.content()["RechazoPrevio"] == "S"
    assert cancel.previous is not None
    assert cancel.previous.hash == fix.hash
    assert cancel.previous.series_number == "F-2026-0001"


@pytest.mark.req("RN-F-07")
def test_la_cadena_rota_se_detecta(invoice):
    first = alta(invoice)
    second = alta(invoice, first)
    third = alta(invoice, second)
    with pytest.raises(InvalidBillingRecordError, match="registro 1"):
        verify_chain([first, third])
    with pytest.raises(InvalidBillingRecordError, match="registro 0"):
        verify_chain([second])


@pytest.mark.req("RN-F-07")
def test_una_sola_cadena_por_cuenta(invoice):
    other = dataclasses.replace(issue(draft(line("1.00"))), tenant_id=TenantId(uuid4()))
    with pytest.raises(InvalidBillingRecordError):
        alta(other, alta(invoice))
    foreign_first = alta(other)
    # Un registro de otra cuenta que enlazara con este no se puede crear con
    # las fábricas; se fuerza para comprobar que la verificación lo detecta.
    mixed = dataclasses.replace(alta(other, foreign_first), tenant_id=invoice.tenant_id)
    with pytest.raises(InvalidBillingRecordError, match="cuentas"):
        verify_chain([foreign_first, mixed])


@pytest.mark.req("RN-F-07")
def test_un_registro_no_es_anterior_al_que_le_precede(invoice):
    first = alta(invoice)
    with pytest.raises(InvalidBillingRecordError):
        alta(invoice, first, generated_at=NOW - timedelta(seconds=1))
    same_second = alta(invoice, first, generated_at=NOW + timedelta(microseconds=500))
    assert same_second.generated_at == NOW


@pytest.mark.req("RN-F-07")
def test_registros_no_validos(invoice):
    with pytest.raises(InvalidBillingRecordError):
        alta(draft(line("1.00")))
    with pytest.raises(InvalidBillingRecordError):
        alta(invoice, prior_rejection=True)
    with pytest.raises(InvalidBillingRecordError):
        alta(invoice, generated_at=NOW.replace(tzinfo=None))
    record = alta(invoice)
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, generated_at=NOW.replace(tzinfo=None))
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, series_number="F" * 61)
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, external_ref="x" * 61)
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(record, error_description="x" * 1501)
    cancel = anulacion(invoice, None)
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(cancel, is_correction=True)
    with pytest.raises(InvalidBillingRecordError):
        ChainLink(
            issuer_tax_id=TaxId("12345678Z"),
            series_number="F-2026-0001",
            issue_date=TODAY,
            hash="abc",
        )


@pytest.mark.req("RN-F-07")
@pytest.mark.parametrize(
    "changes",
    [
        {"producer_name": ""},
        {"system_name": "x" * 31},
        {"version": "x" * 51},
        {"installation_number": "x" * 101},
        {"system_id": "K"},
        {"system_id": "K-"},
    ],
)
def test_datos_del_sistema_no_validos(changes):
    with pytest.raises(InvalidBillingRecordError):
        dataclasses.replace(SYSTEM, **changes)


@pytest.mark.req("RN-F-07")
def test_el_envio_no_toca_contenido_ni_huella(invoice):
    record = alta(invoice)
    sent = record.with_submission_result(
        status=SubmissionStatus.REJECTED,
        submitted_at=NOW,
        error_code="1100",
        error_description="Valor no permitido",
    )
    assert sent.submission_status is SubmissionStatus.REJECTED
    assert (sent.canonical_json, sent.hash) == (record.canonical_json, record.hash)


@pytest.mark.req("RN-F-07")
def test_la_anulacion_se_deduce_de_la_cadena(invoice):
    registration = alta(invoice)
    cancel = anulacion(invoice, registration)
    accepted = SubmissionStatus.ACCEPTED
    assert not is_cancelled([registration, cancel])
    assert not is_cancelled(
        [registration.with_submission_result(status=accepted, submitted_at=NOW), cancel]
    )
    assert is_cancelled(
        [
            registration.with_submission_result(status=accepted, submitted_at=NOW),
            cancel.with_submission_result(
                status=SubmissionStatus.ACCEPTED_WITH_ERRORS, submitted_at=NOW
            ),
        ]
    )
    assert not is_cancelled(
        [
            registration,
            cancel.with_submission_result(status=SubmissionStatus.REJECTED, submitted_at=NOW),
        ]
    )


@pytest.mark.req("RN-F-07")
def test_sistema_de_un_solo_obligado():
    system = SystemInfo(
        producer_name="KodigoLab",
        producer_tax_id=TaxId("A58818501"),
        system_name="Kapataz",
        system_id="K1",
        version="1.0.0",
        installation_number="1",
        only_verifactu=True,
        multi_taxpayer=False,
        has_multiple_taxpayers=False,
    )
    assert system.canonical()["IndicadorMultiplesOT"] == "N"
