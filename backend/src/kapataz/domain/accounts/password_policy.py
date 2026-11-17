"""Política de contraseñas (ADR-025)."""

from kapataz.domain.accounts.errors import WeakPasswordError

MIN_PASSWORD_LENGTH = 12
# Tope para que nadie convierta el cálculo de Argon2id en una denegación de
# servicio enviando contraseñas de megas.
MAX_PASSWORD_LENGTH = 1024


def check_password_policy(plain: str) -> None:
    """Rechaza contraseñas demasiado cortas, demasiado largas o solo de espacios."""
    if not MIN_PASSWORD_LENGTH <= len(plain) <= MAX_PASSWORD_LENGTH:
        msg = (
            f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} "
            f"y {MAX_PASSWORD_LENGTH} caracteres."
        )
        raise WeakPasswordError(msg)
    if not plain.strip():
        msg = "La contraseña no puede ser solo espacios."
        raise WeakPasswordError(msg)
