"""Códigos de facturación compartidos por presupuestos, facturas y registros.

Los valores coinciden con los que guarda la base de datos (plan §4.5) y, cuando
existen, con los del registro de la AEAT (TipoFactura, TipoRectificativa).
"""

from enum import StrEnum


class InvoiceStatus(StrEnum):
    """Estado fiscal. El de cobro es otro y sale de los cobros (RF-FA-06)."""

    DRAFT = "draft"
    ISSUED = "issued"


class InvoiceType(StrEnum):
    """TipoFactura del registro de la AEAT.

    La v1 emite F1 (factura completa) y R1 a R4 (rectificativas). F2
    (simplificada), F3 (sustitutiva de simplificadas) y R5 (rectificativa de
    simplificadas) quedan reservadas: la v1 no emite facturas simplificadas
    (RN-F-06, plan §1.4).
    """

    F1 = "F1"
    F2 = "F2"
    F3 = "F3"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"

    @property
    def is_corrective(self) -> bool:
        return self.value.startswith("R")

    @property
    def is_supported(self) -> bool:
        return self in _SUPPORTED_INVOICE_TYPES


_SUPPORTED_INVOICE_TYPES = frozenset(
    {InvoiceType.F1, InvoiceType.R1, InvoiceType.R2, InvoiceType.R3, InvoiceType.R4},
)


class CorrectionType(StrEnum):
    """Rectificación por sustitución o por diferencias (RN-F-03)."""

    SUBSTITUTION = "substitution"
    DIFFERENCE = "difference"

    @property
    def aeat_code(self) -> str:
        """TipoRectificativa del registro de la AEAT: S o I."""
        return "S" if self is CorrectionType.SUBSTITUTION else "I"


class PhaseType(StrEnum):
    """Fase de facturación de un presupuesto (RF-FA-10, ``BillingPhase``).

    ``FULL`` es la factura completa de una vez; también la usa una factura que
    no sale de ningún presupuesto.
    """

    FULL = "full"
    ADVANCE = "advance"
    PROGRESS = "progress"
    FINAL = "final"


class LineOrigin(StrEnum):
    """De dónde sale una línea de factura (RF-FA-12, RN-F-12).

    ``ADDITIONAL`` es el trabajo adicional (``AdditionalWork``): se marca en la
    app, pero la factura no lo distingue. ``PRIOR_INVOICE`` resta, en la fase
    final, la base de una factura anterior citándola.
    """

    QUOTE = "quote"
    ADDITIONAL = "additional"
    PRIOR_INVOICE = "prior_invoice"


class RecipientType(StrEnum):
    """Quién recibe la obra, para decidir el tipo de IVA (RN-F-13).

    ``PRIVATE`` es una persona física que usa la vivienda para fines
    particulares. La vivienda alquilada como vivienda habitual del RDL 29/2026
    está pendiente de decidir (HANDOFF, Bloque 8).
    """

    PRIVATE = "private"
    COMMUNITY = "community"
    BUSINESS = "business"
