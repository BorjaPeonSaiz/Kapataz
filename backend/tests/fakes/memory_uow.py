"""Unidad de trabajo en memoria para las pruebas de API sin PostgreSQL.

Imita lo que importa de la real: la transacción se deshace si no hay commit,
el email es único y ``tenants`` exige la cuenta fijada (como la política RLS).
Las pruebas de integración repiten los flujos contra PostgreSQL real.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from kapataz.application.ports.persistence import AccountRepository, UnitOfWork
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import EmailAlreadyRegisteredError
from kapataz.domain.accounts.model import (
    EmailVerification,
    Session,
    SessionId,
    Tenant,
    TenantId,
    User,
    UserId,
)


@dataclass
class MemoryState:
    tenants: dict[TenantId, Tenant] = field(default_factory=dict)
    users: dict[UserId, User] = field(default_factory=dict)
    sessions: dict[SessionId, tuple[Session, str]] = field(default_factory=dict)
    verifications: dict[UUID, tuple[EmailVerification, str]] = field(default_factory=dict)

    def copy(self) -> "MemoryState":
        return MemoryState(
            tenants=dict(self.tenants),
            users=dict(self.users),
            sessions=dict(self.sessions),
            verifications=dict(self.verifications),
        )


class MemoryAccounts:
    def __init__(self, state: MemoryState, uow: "MemoryUnitOfWork") -> None:
        self._s = state
        self._uow = uow

    async def add_tenant(self, tenant: Tenant) -> None:
        if self._uow.tenant_id != tenant.id:
            msg = "RLS: la cuenta fijada no coincide con la fila (WITH CHECK)."
            raise PermissionError(msg)
        self._s.tenants[tenant.id] = tenant

    async def add_user(self, user: User) -> None:
        if any(u.email == user.email for u in self._s.users.values()):
            msg = "Email ya registrado."
            raise EmailAlreadyRegisteredError(msg)
        self._s.users[user.id] = user

    async def get_user_by_email(self, email: EmailAddress) -> User | None:
        return next((u for u in self._s.users.values() if u.email == email.value), None)

    async def mark_email_verified(self, user_id: UserId, at: datetime) -> None:
        user = self._s.users[user_id]
        if user.email_verified_at is None:
            self._s.users[user_id] = replace(user, email_verified_at=at)

    async def add_email_verification(
        self, verification: EmailVerification, token_hash: str
    ) -> None:
        self._s.verifications[verification.id] = (verification, token_hash)

    async def get_email_verification_for_update(self, token_hash: str) -> EmailVerification | None:
        return next((v for v, h in self._s.verifications.values() if h == token_hash), None)

    async def mark_email_verification_used(self, verification_id: UUID, at: datetime) -> None:
        verification, token_hash = self._s.verifications[verification_id]
        self._s.verifications[verification_id] = (replace(verification, used_at=at), token_hash)

    async def add_session(self, session: Session, token_hash: str) -> None:
        self._s.sessions[session.id] = (session, token_hash)

    async def get_session_with_user(self, token_hash: str) -> tuple[Session, User] | None:
        for session, stored_hash in self._s.sessions.values():
            if stored_hash == token_hash:
                return session, self._s.users[session.user_id]
        return None

    async def touch_session(self, session_id: SessionId, at: datetime) -> None:
        session, token_hash = self._s.sessions[session_id]
        self._s.sessions[session_id] = (replace(session, last_seen_at=at), token_hash)

    async def revoke_session(self, session_id: SessionId, at: datetime) -> None:
        session, token_hash = self._s.sessions[session_id]
        if session.revoked_at is None:
            self._s.sessions[session_id] = (replace(session, revoked_at=at), token_hash)


class MemoryUnitOfWork:
    def __init__(self, store: "MemoryUnitOfWorkFactory") -> None:
        self._store = store
        self._working = store.state.copy()
        self._accounts = MemoryAccounts(self._working, self)
        self.tenant_id: TenantId | None = None

    @property
    def accounts(self) -> AccountRepository:
        return self._accounts

    async def set_tenant(self, tenant_id: TenantId) -> None:
        self.tenant_id = tenant_id

    async def commit(self) -> None:
        self._store.state = self._working.copy()


class MemoryUnitOfWorkFactory:
    def __init__(self) -> None:
        self.state = MemoryState()

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[UnitOfWork]:
        yield MemoryUnitOfWork(self)
