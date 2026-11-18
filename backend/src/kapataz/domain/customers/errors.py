"""Errores de clientes."""

from kapataz.domain.errors import DomainError


class InvalidTaxIdError(DomainError):
    """El NIF no tiene el formato o el dígito de control de un NIF español."""

    slug = "nif-no-valido"


class InvalidCustomerError(DomainError):
    slug = "cliente-no-valido"
