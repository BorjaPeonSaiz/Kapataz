"""Entidades de cuentas: Tenant, User, Session y EmailVerification."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)
SessionId = NewType("SessionId", UUID)

SESSION_TTL = timedelta(days=14)
# La última actividad de una sesión se actualiza como mucho cada cinco minutos,
# para no escribir en la base de datos en cada petición.
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
EMAIL_VERIFICATION_TTL = timedelta(hours=24)


class TenantKind(StrEnum):
    STANDARD = "standard"
    DEMO = "demo"


@dataclass(frozen=True, slots=True)
class Tenant:
    """Cuenta. Un espacio de demostración pertenece a otra cuenta (RF-CF-04, RN-13).

    ``name`` es None hasta que el profesional da sus datos; nunca es el email.
    """

    id: TenantId
    name: str | None
    kind: TenantKind
    parent_tenant_id: TenantId | None
    created_at: datetime

    def __post_init__(self) -> None:
        if (self.kind is TenantKind.DEMO) != (self.parent_tenant_id is not None):
            msg = "Un espacio de demostración, y solo él, tiene cuenta padre."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class User:
    id: UserId
    tenant_id: TenantId
    email: str
    password_hash: str
    email_verified_at: datetime | None
    created_at: datetime

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None


@dataclass(frozen=True, slots=True)
class Session:
    id: SessionId
    user_id: UserId
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at

    def needs_touch(self, now: datetime) -> bool:
        return now - self.last_seen_at >= SESSION_TOUCH_INTERVAL


@dataclass(frozen=True, slots=True)
class EmailVerification:
    id: UUID
    user_id: UserId
    expires_at: datetime
    used_at: datetime | None

    def is_usable(self, now: datetime) -> bool:
        """Un enlace sirve una sola vez y antes de caducar (ADR-025)."""
        return self.used_at is None and now < self.expires_at


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Quién hace la petición y en qué cuenta trabaja."""

    user_id: UserId
    tenant_id: TenantId
    email: str
    session_id: SessionId
