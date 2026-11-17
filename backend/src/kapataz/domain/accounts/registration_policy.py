"""Quién puede registrarse (RF-AC-01 y su excepción RN-13)."""

from dataclasses import dataclass, field

from kapataz.domain.accounts.email_address import EmailAddress


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    """Registro abierto o cerrado con lista de emails habilitados.

    RN-13: mientras queden pendientes legales, el registro está cerrado y solo se registran los
    emails que habilita el superadministrador (RF-SA-07). En el Bloque 1 la
    lista llega por configuración; el Bloque 10 la mueve a ``platform_settings``.
    """

    is_open: bool = False
    allowlist: frozenset[EmailAddress] = field(default_factory=frozenset)

    def allows(self, email: EmailAddress) -> bool:
        return self.is_open or email in self.allowlist
