"""Entidad Professional: datos fiscales del emisor, una por cuenta (RF-CF-01, RN-F-06).

Es lo mínimo que necesita la emisión: nombre o razón social, NIF y domicilio.
El asistente de primer arranque (RF-CF-01) puede guardarlos a medias, por eso
el NIF y el domicilio son opcionales aquí y se exigen al emitir, igual que en
``Customer``. El logotipo, las series, el IVA por defecto y las condiciones de
pago llegan con el asistente.
"""

from dataclasses import dataclass
from datetime import datetime

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.aeat_limits import MAX_PARTY_NAME_LENGTH
from kapataz.domain.customers.model import MAX_ADDRESS_LENGTH, is_valid_address
from kapataz.domain.customers.tax_id import TaxId
from kapataz.domain.errors import DomainError


class InvalidProfessionalError(DomainError):
    slug = "datos-del-profesional-no-validos"


@dataclass(frozen=True, slots=True, kw_only=True)
class Professional:
    """Emisor de las facturas de una cuenta. Mismas reglas de nombre y domicilio que ``Party``."""

    tenant_id: TenantId
    name: str
    tax_id: TaxId | None
    address: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise InvalidProfessionalError("El nombre o razón social no puede estar vacío.")
        if len(self.name) > MAX_PARTY_NAME_LENGTH:
            msg = f"El nombre o razón social admite {MAX_PARTY_NAME_LENGTH} caracteres."
            raise InvalidProfessionalError(msg)
        if self.address is not None and not is_valid_address(self.address):
            msg = f"El domicilio no puede estar vacío y admite {MAX_ADDRESS_LENGTH} caracteres."
            raise InvalidProfessionalError(msg)
        if self.updated_at.tzinfo is None:
            raise InvalidProfessionalError("La fecha de cambio debe llevar zona horaria.")
