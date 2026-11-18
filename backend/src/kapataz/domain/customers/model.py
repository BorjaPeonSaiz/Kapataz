"""Entidad Customer: destinatario de presupuestos y facturas."""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType
from uuid import UUID

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.aeat_limits import MAX_PARTY_NAME_LENGTH
from kapataz.domain.customers.errors import InvalidCustomerError
from kapataz.domain.customers.tax_id import TaxId

CustomerId = NewType("CustomerId", UUID)

# El domicilio es obligatorio en la factura completa (art. 6 del RD 1619/2012,
# RN-F-06), pero ni el reglamento ni el registro de la AEAT, que no lo lleva,
# fijan una longitud. 250 caracteres caben de sobra en una dirección española
# completa (vía, número, piso, código postal, municipio y provincia) y dejan
# fuera textos que solo pueden ser un error.
MAX_ADDRESS_LENGTH = 250


def is_valid_address(address: str) -> bool:
    """Domicilio sin espacios al principio ni al final, no vacío y de 250 como mucho."""
    return (
        bool(address.strip())
        and address == address.strip()
        and (len(address) <= MAX_ADDRESS_LENGTH)
    )


@dataclass(frozen=True, slots=True)
class Customer:
    """Cliente de una cuenta.

    El NIF es opcional porque el histórico importado trae clientes sin él
    (RF-IN-08), y el domicilio por lo mismo. Emitir una factura exige los dos
    (RN-F-06): esa comprobación se hace al emitir, no aquí, para poder guardar
    el cliente mientras tanto.
    """

    id: CustomerId
    tenant_id: TenantId
    name: str
    tax_id: TaxId | None
    address: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise InvalidCustomerError("El nombre del cliente no puede estar vacío.")
        if len(self.name) > MAX_PARTY_NAME_LENGTH:
            msg = f"El nombre del cliente admite como mucho {MAX_PARTY_NAME_LENGTH} caracteres."
            raise InvalidCustomerError(msg)
        if self.address is not None and not is_valid_address(self.address):
            msg = (
                f"El domicilio no puede estar vacío ni tener espacios en los bordes, "
                f"y admite {MAX_ADDRESS_LENGTH} caracteres."
            )
            raise InvalidCustomerError(msg)
        if self.created_at.tzinfo is None:
            raise InvalidCustomerError("La fecha de alta debe llevar zona horaria.")
