"""Entidad CatalogItem: concepto facturable genérico («punto de luz», RF-CF-02)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.money import Money
from kapataz.domain.errors import DomainError

CatalogItemId = NewType("CatalogItemId", UUID)

MAX_CONCEPT_LENGTH = 200
MAX_UNIT_LENGTH = 20


class InvalidCatalogItemError(DomainError):
    slug = "concepto-no-valido"


class CatalogItemOrigin(StrEnum):
    """De dónde sale el concepto: lo creó el usuario o salió del histórico (RF-CF-02)."""

    MANUAL = "manual"
    HISTORY = "history"


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogItem:
    """Concepto con unidad y precio de referencia opcional.

    ``is_material`` es la marca por defecto de las líneas que salen de este
    concepto, para el límite del 40 % (RN-F-13); la línea la puede cambiar.
    """

    id: CatalogItemId
    tenant_id: TenantId
    concept: str
    unit: str
    reference_price: Money | None
    origin: CatalogItemOrigin
    is_material: bool
    created_at: datetime

    def __post_init__(self) -> None:
        for value, limit in ((self.concept, MAX_CONCEPT_LENGTH), (self.unit, MAX_UNIT_LENGTH)):
            if not value.strip() or value != value.strip() or len(value) > limit:
                raise InvalidCatalogItemError("Concepto o unidad vacíos o demasiado largos.")
        if self.reference_price is not None and not self.reference_price.is_positive():
            raise InvalidCatalogItemError("El precio de referencia es mayor que cero.")
        if self.created_at.tzinfo is None:
            raise InvalidCatalogItemError("La fecha de alta debe llevar zona horaria.")
