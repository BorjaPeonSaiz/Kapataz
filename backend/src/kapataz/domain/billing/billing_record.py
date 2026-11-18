"""Registro de facturación (``BillingRecord``) y su cadena (RN-F-07, RF-VF-01, ADR-012).

Hay una sola cadena por cuenta, con altas, subsanaciones y anulaciones de
todas las series. Cada registro guarda su contenido canónico, con los nombres
de campo de ``RegistroAlta`` y ``RegistroAnulacion`` de la AEAT (Orden
HAC/1177/2024, arts. 7 y 13), y su huella, que enlaza con la del registro
anterior.

La huella sigue el algoritmo oficial de la AEAT («Detalle de las
especificaciones técnicas para generación de la huella o hash de los registros
de facturación», v0.1.2, 27/08/2024): SHA-256, en hexadecimal en mayúsculas, de
una cadena ``campo=valor`` unida con ``&`` con unos pocos campos del registro,
entre ellos la huella del anterior. Esos campos se leen del propio contenido
canónico, así que la huella y lo que se enviará en el XML no pueden discrepar.
El Bloque 12 solo convierte el contenido a XML y lo envía.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Final, Self

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.aeat_limits import (
    MAX_ERROR_DESCRIPTION_LENGTH,
    MAX_EXTERNAL_REF_LENGTH,
    MAX_INSTALLATION_NUMBER_LENGTH,
    MAX_PARTY_NAME_LENGTH,
    MAX_SERIES_NUMBER_LENGTH,
    MAX_SYSTEM_NAME_LENGTH,
    MAX_SYSTEM_VERSION_LENGTH,
    SYSTEM_ID_LENGTH,
)
from kapataz.domain.billing.errors import InvalidBillingRecordError
from kapataz.domain.billing.ids import BillingRecordId, InvoiceId
from kapataz.domain.billing.invoice import CorrectiveInvoice, Invoice
from kapataz.domain.customers.tax_id import TaxId

type CanonicalValue = str | list[CanonicalValue] | dict[str, CanonicalValue]
type CanonicalContent = dict[str, CanonicalValue]

ID_VERSION: Final = "1.0"
# TipoHuella 01: SHA-256.
HASH_TYPE: Final = "01"
# Impuesto 01: IVA.
VAT_TAX_CODE: Final = "01"
_HASH_PATTERN = re.compile(r"^[0-9A-F]{64}$")

# Campos obligatorios de primer nivel de cada tipo de registro, según los
# esquemas de la AEAT. La prueba de campos obligatorios los recorre.
REGISTRATION_REQUIRED_FIELDS: Final = (
    "IDVersion",
    "IDFactura",
    "NombreRazonEmisor",
    "TipoFactura",
    "DescripcionOperacion",
    "Destinatarios",
    "Desglose",
    "CuotaTotal",
    "ImporteTotal",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
)
CANCELLATION_REQUIRED_FIELDS: Final = (
    "IDVersion",
    "IDFactura",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
)


class RecordType(StrEnum):
    REGISTRATION = "registration"
    CANCELLATION = "cancellation"


class SubmissionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    ACCEPTED_WITH_ERRORS = "accepted_with_errors"
    REJECTED = "rejected"

    @property
    def is_accepted(self) -> bool:
        """La AEAT ha registrado el registro, con o sin errores admisibles."""
        return self in {SubmissionStatus.ACCEPTED, SubmissionStatus.ACCEPTED_WITH_ERRORS}


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemInfo:
    """Bloque SistemaInformatico: quién produce el sistema y qué instalación genera el registro.

    ``version`` es, antes de la 1.0.0, el identificador del commit (ADR-032).
    """

    producer_name: str
    producer_tax_id: TaxId
    system_name: str
    system_id: str
    version: str
    installation_number: str
    only_verifactu: bool
    multi_taxpayer: bool
    has_multiple_taxpayers: bool

    def __post_init__(self) -> None:
        for value, limit in (
            (self.producer_name, MAX_PARTY_NAME_LENGTH),
            (self.system_name, MAX_SYSTEM_NAME_LENGTH),
            (self.version, MAX_SYSTEM_VERSION_LENGTH),
            (self.installation_number, MAX_INSTALLATION_NUMBER_LENGTH),
        ):
            if not value.strip() or len(value) > limit:
                raise InvalidBillingRecordError("Dato del sistema vacío o demasiado largo.")
        if len(self.system_id) != SYSTEM_ID_LENGTH or not self.system_id.isalnum():
            raise InvalidBillingRecordError("El id del sistema son dos caracteres alfanuméricos.")

    def canonical(self) -> CanonicalContent:
        return {
            "NombreRazon": self.producer_name,
            "NIF": str(self.producer_tax_id),
            "NombreSistemaInformatico": self.system_name,
            "IdSistemaInformatico": self.system_id,
            "Version": self.version,
            "NumeroInstalacion": self.installation_number,
            "TipoUsoPosibleSoloVerifactu": _yes_no(self.only_verifactu),
            "TipoUsoPosibleMultiOT": _yes_no(self.multi_taxpayer),
            "IndicadorMultiplesOT": _yes_no(self.has_multiple_taxpayers),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ChainLink:
    """Datos del registro anterior que enlaza el siguiente (RegistroAnterior)."""

    issuer_tax_id: TaxId
    series_number: str
    issue_date: date
    hash: str

    def __post_init__(self) -> None:
        if not _HASH_PATTERN.fullmatch(self.hash):
            raise InvalidBillingRecordError("Huella no válida.")

    def canonical(self) -> CanonicalContent:
        return {
            "IDEmisorFactura": str(self.issuer_tax_id),
            "NumSerieFactura": self.series_number,
            "FechaExpedicionFactura": _aeat_date(self.issue_date),
            "Huella": self.hash,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BillingRecord:
    """Registro de alta, subsanación o anulación de una factura.

    El contenido y la huella no cambian nunca. Lo único que cambia es el
    resultado del envío (``with_submission_result``), en el Bloque 12.
    Al construirlo se comprueba que la huella corresponde al contenido: un
    registro alterado no se puede ni cargar sin que se note.
    """

    id: BillingRecordId
    tenant_id: TenantId
    invoice_id: InvoiceId
    record_type: RecordType
    is_correction: bool
    prior_rejection: bool
    issuer_tax_id: TaxId
    series_number: str
    issue_date: date
    previous: ChainLink | None
    system: SystemInfo
    generated_at: datetime
    external_ref: str | None
    canonical_json: str
    hash: str
    submission_status: SubmissionStatus = SubmissionStatus.PENDING
    error_code: str | None = None
    error_description: str | None = None
    submission_csv: str | None = None
    submitted_at: datetime | None = None
    sent_with_incident: bool = False

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise InvalidBillingRecordError("La hora de generación lleva huso horario.")
        if len(self.series_number) > MAX_SERIES_NUMBER_LENGTH:
            raise InvalidBillingRecordError("Serie y número demasiado largos.")
        if self.external_ref is not None and len(self.external_ref) > MAX_EXTERNAL_REF_LENGTH:
            raise InvalidBillingRecordError("La referencia externa es demasiado larga.")
        if (
            self.error_description is not None
            and len(self.error_description) > MAX_ERROR_DESCRIPTION_LENGTH
        ):
            raise InvalidBillingRecordError("La descripción del error es demasiado larga.")
        is_registration = self.record_type is RecordType.REGISTRATION
        # RechazoPrevio=S en un alta solo cabe en una subsanación.
        if is_registration and self.prior_rejection and not self.is_correction:
            raise InvalidBillingRecordError("Un rechazo previo se subsana.")
        if not is_registration and self.is_correction:
            raise InvalidBillingRecordError("Una anulación no es una subsanación.")
        content = self.content()
        # El enlace guardado aparte y el del contenido son el mismo: si no, la
        # cadena que se verifica y la que se envía podrían ser distintas.
        if content.get("Encadenamiento") != _chain(self.previous):
            raise InvalidBillingRecordError("El encadenamiento no cuadra con el contenido.")
        if compute_record_hash(self.record_type, content) != self.hash:
            raise InvalidBillingRecordError("La huella no corresponde al contenido.")

    @property
    def is_first(self) -> bool:
        return self.previous is None

    def as_link(self) -> ChainLink:
        """Enlace que llevará el registro siguiente de la cadena."""
        return ChainLink(
            issuer_tax_id=self.issuer_tax_id,
            series_number=self.series_number,
            issue_date=self.issue_date,
            hash=self.hash,
        )

    def content(self) -> CanonicalContent:
        loaded: CanonicalContent = json.loads(self.canonical_json)
        return loaded

    def with_submission_result(
        self,
        *,
        status: SubmissionStatus,
        submitted_at: datetime,
        error_code: str | None = None,
        error_description: str | None = None,
        submission_csv: str | None = None,
    ) -> Self:
        """Resultado del envío a la AEAT. El contenido y la huella no se tocan."""
        return replace(
            self,
            submission_status=status,
            submitted_at=submitted_at,
            error_code=error_code,
            error_description=error_description,
            submission_csv=submission_csv,
        )


def registration_hash_input(
    *,
    issuer_tax_id: str,
    series_number: str,
    issue_date: str,
    invoice_type: str,
    tax_total: str,
    total_amount: str,
    previous_hash: str,
    generated_at: str,
) -> str:
    """Cadena de la huella de un alta, con los campos en el orden oficial.

    Recibe los valores tal como van en el XML: fechas ``dd-mm-aaaa``, importes
    con punto decimal y ``generated_at`` en ISO 8601 con huso. ``previous_hash``
    va vacío en el primer registro (``…&Huella=&…``).
    """
    return _join_fields(
        ("IDEmisorFactura", issuer_tax_id),
        ("NumSerieFactura", series_number),
        ("FechaExpedicionFactura", issue_date),
        ("TipoFactura", invoice_type),
        ("CuotaTotal", tax_total),
        ("ImporteTotal", total_amount),
        ("Huella", previous_hash),
        ("FechaHoraHusoGenRegistro", generated_at),
    )


def cancellation_hash_input(
    *,
    issuer_tax_id: str,
    series_number: str,
    issue_date: str,
    previous_hash: str,
    generated_at: str,
) -> str:
    """Cadena de la huella de una anulación, con los campos en el orden oficial."""
    return _join_fields(
        ("IDEmisorFacturaAnulada", issuer_tax_id),
        ("NumSerieFacturaAnulada", series_number),
        ("FechaExpedicionFacturaAnulada", issue_date),
        ("Huella", previous_hash),
        ("FechaHoraHusoGenRegistro", generated_at),
    )


def sha256_hash(hash_input: str) -> str:
    """SHA-256 de la cadena en UTF-8, en hexadecimal en mayúsculas (64 caracteres)."""
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest().upper()


def compute_record_hash(record_type: RecordType, content: CanonicalContent) -> str:
    """Huella oficial de un registro a partir de su contenido canónico."""
    chain = _mapping(content, "Encadenamiento")
    previous = chain.get("RegistroAnterior")
    previous_hash = "" if previous is None else _text(_as_mapping(previous), "Huella")
    invoice_id = _mapping(content, "IDFactura")
    generated_at = _text(content, "FechaHoraHusoGenRegistro")
    if record_type is RecordType.REGISTRATION:
        hash_input = registration_hash_input(
            issuer_tax_id=_text(invoice_id, "IDEmisorFactura"),
            series_number=_text(invoice_id, "NumSerieFactura"),
            issue_date=_text(invoice_id, "FechaExpedicionFactura"),
            invoice_type=_text(content, "TipoFactura"),
            tax_total=_text(content, "CuotaTotal"),
            total_amount=_text(content, "ImporteTotal"),
            previous_hash=previous_hash,
            generated_at=generated_at,
        )
    else:
        hash_input = cancellation_hash_input(
            issuer_tax_id=_text(invoice_id, "IDEmisorFacturaAnulada"),
            series_number=_text(invoice_id, "NumSerieFacturaAnulada"),
            issue_date=_text(invoice_id, "FechaExpedicionFacturaAnulada"),
            previous_hash=previous_hash,
            generated_at=generated_at,
        )
    return sha256_hash(hash_input)


def canonical_json(content: Mapping[str, CanonicalValue]) -> str:
    """Serialización única: claves ordenadas, sin espacios, UTF-8 sin escapar.

    Dos contenidos iguales dan siempre el mismo texto y, por tanto, la misma huella.
    """
    return json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def registration_record(
    *,
    record_id: BillingRecordId,
    invoice: Invoice,
    previous: BillingRecord | None,
    system: SystemInfo,
    generated_at: datetime,
    is_correction: bool = False,
    prior_rejection: bool = False,
    external_ref: str | None = None,
) -> BillingRecord:
    """Registro de alta (o de subsanación) de una factura emitida.

    ``previous`` es el último registro de la cadena de la cuenta, leído con la
    cabeza de la cadena bloqueada (RN-F-07). ``generated_at`` sale del Clock.
    """
    issued = _require_issued(invoice)
    _check_previous(invoice.tenant_id, previous, generated_at)
    link = None if previous is None else previous.as_link()
    content = _registration_content(
        issued, link, system, generated_at, is_correction, prior_rejection, external_ref
    )
    return _build(
        record_id=record_id,
        issued=issued,
        record_type=RecordType.REGISTRATION,
        is_correction=is_correction,
        prior_rejection=prior_rejection,
        link=link,
        system=system,
        generated_at=generated_at,
        external_ref=external_ref,
        content=content,
    )


def cancellation_record(
    *,
    record_id: BillingRecordId,
    invoice: Invoice,
    previous: BillingRecord | None,
    system: SystemInfo,
    generated_at: datetime,
    prior_rejection: bool = False,
    external_ref: str | None = None,
) -> BillingRecord:
    """Registro de anulación. La factura no cambia: el estado sale de la cadena (RN-F-07)."""
    issued = _require_issued(invoice)
    _check_previous(invoice.tenant_id, previous, generated_at)
    link = None if previous is None else previous.as_link()
    content: CanonicalContent = {
        "IDVersion": ID_VERSION,
        "IDFactura": {
            "IDEmisorFacturaAnulada": str(issued.issuer_tax_id),
            "NumSerieFacturaAnulada": issued.series_number,
            "FechaExpedicionFacturaAnulada": _aeat_date(issued.issue_date),
        },
        "SinRegistroPrevio": "N",
        "RechazoPrevio": _yes_no(prior_rejection),
        **_tail(link, system, generated_at),
    }
    if external_ref is not None:
        content["RefExterna"] = external_ref
    return _build(
        record_id=record_id,
        issued=issued,
        record_type=RecordType.CANCELLATION,
        is_correction=False,
        prior_rejection=prior_rejection,
        link=link,
        system=system,
        generated_at=generated_at,
        external_ref=external_ref,
        content=content,
    )


def is_cancelled(records: Iterable[BillingRecord]) -> bool:
    """Si una factura está anulada, según sus registros en el orden de la cadena.

    Lo está si su último registro aceptado por la AEAT es una anulación
    (RN-F-07). Mientras no haya envío (hasta el Bloque 12), ninguno está
    aceptado y ninguna factura figura como anulada.
    """
    last_accepted: BillingRecord | None = None
    for record in records:
        if record.submission_status.is_accepted:
            last_accepted = record
    return last_accepted is not None and last_accepted.record_type is RecordType.CANCELLATION


def verify_chain(records: Sequence[BillingRecord]) -> None:
    """Comprueba una cadena completa de una cuenta, del primer registro al último.

    Cada huella corresponde a su contenido (lo comprueba ``BillingRecord``) y
    cada registro enlaza con el anterior. Lanza ``InvalidBillingRecordError``
    con la posición del primer registro roto.
    """
    previous: BillingRecord | None = None
    for position, record in enumerate(records):
        expected = None if previous is None else previous.as_link()
        if record.previous != expected:
            msg = f"La cadena se rompe en el registro {position}."
            raise InvalidBillingRecordError(msg)
        if previous is not None and record.tenant_id != previous.tenant_id:
            raise InvalidBillingRecordError("Una cadena no mezcla cuentas.")
        previous = record


# ---------------------------------------------------------------- internas


@dataclass(frozen=True, slots=True)
class _IssuedData:
    """Lo que el registro necesita de una factura ya emitida, sin opcionales."""

    invoice: Invoice
    issuer_tax_id: TaxId
    issuer_name: str
    recipient_tax_id: TaxId
    recipient_name: str
    series_number: str
    issue_date: date


def _require_issued(invoice: Invoice) -> _IssuedData:
    if (
        not invoice.is_issued
        or invoice.issuer is None
        or invoice.recipient is None
        or invoice.number is None
        or invoice.issue_date is None
    ):
        raise InvalidBillingRecordError("Solo una factura emitida tiene registro.")
    return _IssuedData(
        invoice=invoice,
        issuer_tax_id=invoice.issuer.tax_id,
        issuer_name=invoice.issuer.name,
        recipient_tax_id=invoice.recipient.tax_id,
        recipient_name=invoice.recipient.name,
        series_number=str(invoice.number),
        issue_date=invoice.issue_date,
    )


def _check_previous(
    tenant_id: TenantId, previous: BillingRecord | None, generated_at: datetime
) -> None:
    if generated_at.tzinfo is None:
        raise InvalidBillingRecordError("La hora de generación lleva huso horario.")
    if previous is None:
        return
    if previous.tenant_id != tenant_id:
        raise InvalidBillingRecordError("Hay una sola cadena por cuenta (RN-F-07).")
    if generated_at < previous.generated_at:
        raise InvalidBillingRecordError("Un registro no puede ser anterior al que le precede.")


def _registration_content(
    issued: _IssuedData,
    link: ChainLink | None,
    system: SystemInfo,
    generated_at: datetime,
    is_correction: bool,  # noqa: FBT001
    prior_rejection: bool,  # noqa: FBT001
    external_ref: str | None,
) -> CanonicalContent:
    invoice = issued.invoice
    totals = invoice.totals
    # La v1 no emite sin descripción: Invoice.issue lo garantiza (RN-F-06).
    description = invoice.description or ""
    content: CanonicalContent = {
        "IDVersion": ID_VERSION,
        "IDFactura": {
            "IDEmisorFactura": str(issued.issuer_tax_id),
            "NumSerieFactura": issued.series_number,
            "FechaExpedicionFactura": _aeat_date(issued.issue_date),
        },
        "NombreRazonEmisor": issued.issuer_name,
        "Subsanacion": _yes_no(is_correction),
        "RechazoPrevio": _yes_no(prior_rejection),
        "TipoFactura": invoice.invoice_type.value,
        "DescripcionOperacion": description,
        "Destinatarios": [
            {"NombreRazon": issued.recipient_name, "NIF": str(issued.recipient_tax_id)},
        ],
        "Desglose": [_breakdown_detail(invoice)],
        "CuotaTotal": str(totals.tax),
        "ImporteTotal": str(totals.total_amount),
        **_tail(link, system, generated_at),
    }
    if invoice.operation_date is not None and invoice.operation_date != issued.issue_date:
        content["FechaOperacion"] = _aeat_date(invoice.operation_date)
    if external_ref is not None:
        content["RefExterna"] = external_ref
    if isinstance(invoice, CorrectiveInvoice):
        content.update(_correction_fields(invoice, issued.issuer_tax_id))
    return content


def _breakdown_detail(invoice: Invoice) -> CanonicalContent:
    treatment = invoice.treatment
    totals = invoice.totals
    # Con inversión del sujeto pasivo (S2) el tipo y la cuota van a cero.
    # Pendiente de contrastar con las validaciones de la AEAT en el Bloque 12.
    rate = "0.00" if treatment.rate is None else f"{treatment.rate.percent:.2f}"
    return {
        "Impuesto": VAT_TAX_CODE,
        "ClaveRegimen": invoice.regime_key.value,
        "CalificacionOperacion": treatment.operation_class.value,
        "TipoImpositivo": rate,
        "BaseImponibleOimporteNoSujeto": str(totals.base),
        "CuotaRepercutida": str(totals.tax),
    }


def _correction_fields(invoice: CorrectiveInvoice, issuer_tax_id: TaxId) -> CanonicalContent:
    fields: CanonicalContent = {
        "TipoRectificativa": invoice.correction_type.aeat_code,
        "FacturasRectificadas": [
            {
                "IDEmisorFactura": str(issuer_tax_id),
                "NumSerieFactura": str(item.number),
                "FechaExpedicionFactura": _aeat_date(item.issue_date),
            }
            for item in invoice.rectified
        ],
    }
    base, tax = invoice.rectified_base_total, invoice.rectified_tax_total
    if base is not None and tax is not None:
        fields["ImporteRectificacion"] = {
            "BaseRectificada": str(base),
            "CuotaRectificada": str(tax),
        }
    return fields


def _tail(link: ChainLink | None, system: SystemInfo, generated_at: datetime) -> CanonicalContent:
    """Campos comunes del final de alta y anulación: cadena, sistema, hora y tipo de huella."""
    return {
        "Encadenamiento": _chain(link),
        "SistemaInformatico": system.canonical(),
        "FechaHoraHusoGenRegistro": _aeat_timestamp(generated_at),
        "TipoHuella": HASH_TYPE,
    }


def _chain(link: ChainLink | None) -> CanonicalContent:
    if link is None:
        return {"PrimerRegistro": "S"}
    return {"RegistroAnterior": link.canonical()}


def _build(
    *,
    record_id: BillingRecordId,
    issued: _IssuedData,
    record_type: RecordType,
    is_correction: bool,
    prior_rejection: bool,
    link: ChainLink | None,
    system: SystemInfo,
    generated_at: datetime,
    external_ref: str | None,
    content: CanonicalContent,
) -> BillingRecord:
    return BillingRecord(
        id=record_id,
        tenant_id=issued.invoice.tenant_id,
        invoice_id=issued.invoice.id,
        record_type=record_type,
        is_correction=is_correction,
        prior_rejection=prior_rejection,
        issuer_tax_id=issued.issuer_tax_id,
        series_number=issued.series_number,
        issue_date=issued.issue_date,
        previous=link,
        system=system,
        generated_at=_to_seconds(generated_at),
        external_ref=external_ref,
        canonical_json=canonical_json(content),
        hash=compute_record_hash(record_type, content),
    )


def _join_fields(*fields: tuple[str, str]) -> str:
    # La especificación pide los valores sin espacios al principio ni al final.
    return "&".join(f"{name}={value.strip()}" for name, value in fields)


def _as_mapping(value: CanonicalValue) -> dict[str, CanonicalValue]:
    if not isinstance(value, dict):
        raise InvalidBillingRecordError("Contenido canónico mal formado.")
    return value


def _mapping(content: CanonicalContent, key: str) -> dict[str, CanonicalValue]:
    value = content.get(key)
    if value is None:
        msg = f"Falta {key} en el contenido canónico."
        raise InvalidBillingRecordError(msg)
    return _as_mapping(value)


def _text(content: CanonicalContent, key: str) -> str:
    value = content.get(key)
    if not isinstance(value, str):
        msg = f"Falta {key} en el contenido canónico."
        raise InvalidBillingRecordError(msg)
    return value


def _yes_no(value: bool) -> str:  # noqa: FBT001
    return "S" if value else "N"


def _aeat_date(value: date) -> str:
    """Formato de fecha del registro de la AEAT: dd-mm-aaaa."""
    return value.strftime("%d-%m-%Y")


def _to_seconds(value: datetime) -> datetime:
    return value.replace(microsecond=0)


def _aeat_timestamp(value: datetime) -> str:
    """Fecha, hora y huso horario con segundos (FechaHoraHusoGenRegistro)."""
    return _to_seconds(value).isoformat(timespec="seconds")
