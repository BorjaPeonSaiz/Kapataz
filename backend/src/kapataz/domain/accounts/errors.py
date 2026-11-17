"""Errores de cuentas y acceso."""

from kapataz.domain.errors import DomainError


class InvalidEmailError(DomainError):
    slug = "email-no-valido"


class WeakPasswordError(DomainError):
    slug = "contrasena-debil"


class RegistrationClosedError(DomainError):
    """RN-13: con el registro cerrado solo se registran los emails habilitados."""

    slug = "registro-cerrado"


class InvalidCredentialsError(DomainError):
    """Mismo error para email inexistente, contraseña mala o email sin verificar.

    Así la respuesta no revela si un email tiene cuenta (ADR-025).
    """

    slug = "credenciales-incorrectas"


class InvalidVerificationLinkError(DomainError):
    """Enlace inexistente, caducado o ya usado: no se distingue cuál."""

    slug = "enlace-no-valido"


class NotAuthenticatedError(DomainError):
    slug = "no-autenticado"


class EmailAlreadyRegisteredError(DomainError):
    """Solo para la CLI de administración; la API nunca lo revela."""

    slug = "email-ya-registrado"


class SubscriptionInactiveError(DomainError):
    """RN-12: sin suscripción activa no se usa la IA."""

    slug = "suscripcion-inactiva"
