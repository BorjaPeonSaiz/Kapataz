"""Configuración desde variables de entorno (pydantic-settings).

La lista de variables es un contrato con plataforma-entrega (Dockerfile,
docker-compose.yml y ``/opt/kapataz/.env``). No se añade ni se renombra ninguna
sin acordarlo. Plantilla en ``backend/.env.example``.
"""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.registration_policy import RegistrationPolicy

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
        # Un error de configuración no debe volcar el valor (podría ser un secreto).
        hide_input_in_errors=True,
    )

    app_env: Literal["local", "production"] = "local"
    # Rol de la aplicación (kapataz_app): sin BYPASSRLS ni propiedad de tablas.
    database_url: str
    # Rol propietario (kapataz_owner): solo lo usa Alembic.
    database_migration_url: str | None = None
    secret_key: SecretStr
    public_base_url: str = "http://localhost:8000"
    llm_backend: Literal["fake"] = "fake"
    # Sin uso hasta el Bloque 6 (ClaudeLlm). Nunca se registra en logs.
    anthropic_api_key: SecretStr | None = None
    registration_open: bool = False
    registration_allowlist: Annotated[tuple[EmailAddress, ...], NoDecode] = ()
    email_backend: Literal["fake", "smtp"] = "fake"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    cookie_secure: bool = True
    git_commit: str = "dev"

    @field_validator("registration_allowlist", mode="before")
    @classmethod
    def _parse_allowlist(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(EmailAddress.parse(item) for item in value.split(",") if item.strip())
        return value

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_long(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            msg = f"SECRET_KEY debe tener al menos {MIN_SECRET_KEY_LENGTH} caracteres."
            raise ValueError(msg)
        return value

    @field_validator("public_base_url")
    @classmethod
    def _public_base_url_is_http(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            msg = "PUBLIC_BASE_URL debe ser una URL http(s) absoluta."
            raise ValueError(msg)
        return value.rstrip("/")

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if self.app_env == "production":
            if not self.cookie_secure:
                msg = "En producción COOKIE_SECURE debe ser true (RNF-12)."
                raise ValueError(msg)
            if not self.public_base_url.startswith("https://"):
                msg = "En producción PUBLIC_BASE_URL debe ser https (RNF-12)."
                raise ValueError(msg)
        if self.email_backend == "smtp" and not (self.smtp_host and self.smtp_from):
            msg = "EMAIL_BACKEND=smtp necesita SMTP_HOST y SMTP_FROM."
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def registration_policy(self) -> RegistrationPolicy:
        return RegistrationPolicy(
            is_open=self.registration_open, allowlist=frozenset(self.registration_allowlist)
        )
