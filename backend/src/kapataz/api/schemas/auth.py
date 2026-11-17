"""Esquemas de la API de cuentas. No exponen entidades del dominio (ADR-002)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from kapataz.domain.accounts.email_address import MAX_EMAIL_LENGTH
from kapataz.domain.accounts.password_policy import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH, json_schema_extra={"format": "email"})
    # El mínimo se documenta en el contrato pero lo comprueba el dominio, que
    # responde con el tipo propio /problemas/contrasena-debil.
    password: str = Field(
        max_length=MAX_PASSWORD_LENGTH,
        json_schema_extra={"minLength": MIN_PASSWORD_LENGTH},
    )


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=MAX_EMAIL_LENGTH, json_schema_extra={"format": "email"})
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    tenant_id: UUID
