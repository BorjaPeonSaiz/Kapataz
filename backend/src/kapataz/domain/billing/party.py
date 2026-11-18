"""Objeto de valor Party: emisor o destinatario tal como figuran en una factura.

La factura emitida guarda una copia de nombre, NIF y domicilio, no solo el id
del cliente: si el cliente cambia de nombre o de domicilio después, la factura
emitida no puede cambiar con él (RN-F-02). El registro de facturación lleva
nombre y NIF (RN-F-07); el domicilio va en la factura (RN-F-06, art. 6 del RD
1619/2012).
"""

from dataclasses import dataclass
from typing import Self

from kapataz.domain.aeat_limits import MAX_PARTY_NAME_LENGTH
from kapataz.domain.billing.errors import InvalidInvoiceError, MissingIssueDataError
from kapataz.domain.customers.model import MAX_ADDRESS_LENGTH, Customer, is_valid_address
from kapataz.domain.customers.tax_id import TaxId


@dataclass(frozen=True, slots=True)
class Party:
    """Emisor o destinatario: nombre, NIF y domicilio.

    ``address`` puede faltar mientras se prepara la emisión, para que
    ``Invoice.issue`` diga qué domicilio falta (``issuer_address`` o
    ``recipient_address``); una factura emitida siempre lo tiene. Mismas
    reglas que el nombre: sin espacios en los bordes, no vacío y con un límite
    de ``MAX_ADDRESS_LENGTH`` (250), porque la AEAT no fija ninguno.
    """

    name: str
    tax_id: TaxId
    address: str | None

    def __post_init__(self) -> None:
        if not self.name.strip() or self.name != self.name.strip():
            raise InvalidInvoiceError("El nombre o razón social no puede estar vacío.")
        if len(self.name) > MAX_PARTY_NAME_LENGTH:
            msg = f"El nombre o razón social admite {MAX_PARTY_NAME_LENGTH} caracteres."
            raise InvalidInvoiceError(msg)
        if self.address is not None and not is_valid_address(self.address):
            msg = f"El domicilio no puede estar vacío y admite {MAX_ADDRESS_LENGTH} caracteres."
            raise InvalidInvoiceError(msg)

    @classmethod
    def recipient_from(cls, customer: Customer) -> Self:
        """Destinatario de una factura completa: exige NIF español y domicilio (RN-F-06)."""
        missing = []
        if customer.tax_id is None:
            missing.append("recipient_tax_id")
        if customer.address is None:
            missing.append("recipient_address")
        if customer.tax_id is None or customer.address is None:
            raise MissingIssueDataError(missing)
        return cls(customer.name, customer.tax_id, customer.address)
