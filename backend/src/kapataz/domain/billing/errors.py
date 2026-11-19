"""Errores de facturación.

Los slugs son estables: la API los traduce a ``/problemas/<slug>`` (RFC 9457).
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from kapataz.domain.errors import DomainError

if TYPE_CHECKING:
    from kapataz.domain.billing.money import Money


class InvalidAmountError(DomainError):
    """Importe, cantidad o porcentaje fuera de lo que admite el dominio."""

    slug = "importe-no-valido"


class InvalidTaxRateError(DomainError):
    slug = "tipo-de-iva-no-valido"


class InvalidSeriesError(DomainError):
    slug = "serie-no-valida"


class InvalidDocumentNumberError(DomainError):
    slug = "numero-no-valido"


class InvalidLineItemError(DomainError):
    slug = "linea-no-valida"


class InvalidInvoiceError(DomainError):
    """El borrador incumple una regla de la factura (tipo, fase, garantía…)."""

    slug = "factura-no-valida"


class InvoiceAlreadyIssuedError(DomainError):
    """RN-F-02: una factura emitida no se modifica; se rectifica."""

    slug = "factura-emitida-inmutable"


class IssuedAmountsMismatchError(DomainError):
    """RN-F-02: los importes guardados de una factura emitida no cuadran con sus líneas.

    Solo pasa si alguien cambia la fila fuera de la app o si cambia el cálculo
    de importes (ADR-009). En los dos casos hay que saberlo: mostrar otros
    importes que los emitidos sería cambiar la factura sin decirlo.
    """

    slug = "factura-emitida-descuadrada"


class MissingIssueDataError(DomainError):
    """RN-F-06: falta algún dato obligatorio para emitir.

    ``missing`` lleva códigos estables (``recipient_tax_id``, ``description``…)
    para que la pantalla de confirmación diga qué falta sin interpretar el texto.
    """

    slug = "faltan-datos-obligatorios"

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("Faltan datos obligatorios para emitir: " + ", ".join(self.missing))


class IssueDateBeforeLastError(DomainError):
    """RN-F-04: la fecha de expedición no puede ser anterior a la última de la serie."""

    slug = "fecha-anterior-a-la-ultima-emitida"


class NegativeInvoiceBaseError(DomainError):
    """RN-F-12: no se emite una factura con base negativa; se rectifica."""

    slug = "base-negativa"


class InvalidQuoteError(DomainError):
    slug = "presupuesto-no-valido"


class InvalidQuoteTransitionError(DomainError):
    """RF-PR-04: el cambio de estado pedido no está permitido desde el actual."""

    slug = "cambio-de-estado-no-permitido"


class QuoteNotEditableError(DomainError):
    """Un presupuesto aceptado, rechazado, caducado o facturado ya no se edita."""

    slug = "presupuesto-no-editable"


class PaymentExceedsPendingError(DomainError):
    """RN-F-10: un cobro no puede superar lo pendiente de la factura."""

    slug = "cobro-superior-al-pendiente"

    def __init__(self, pending: "Money") -> None:
        self.pending = pending
        super().__init__(f"Quedan {pending} € por cobrar.")


class InvalidPaymentError(DomainError):
    slug = "cobro-no-valido"


class InvalidBillingRecordError(DomainError):
    slug = "registro-de-facturacion-no-valido"


class InvalidPhaseError(DomainError):
    """Datos de una fase de facturación que no cuadran (RN-F-12)."""

    slug = "fase-no-valida"


class InvoiceNotFoundError(DomainError):
    """La factura no existe en la cuenta. Una de otra cuenta tampoco existe: 404, nunca 403."""

    slug = "factura-no-encontrada"
