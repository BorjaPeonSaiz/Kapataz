"""Repositorio de cuentas sobre PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from kapataz.infrastructure.persistence.tables import (
    EmailVerificationRow,
    SessionRow,
    TenantRow,
    UserRow,
)

_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


class SqlAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_tenant(self, tenant: Tenant) -> None:
        self._session.add(
            TenantRow(
                id=tenant.id,
                name=tenant.name,
                kind=tenant.kind.value,
                parent_tenant_id=tenant.parent_tenant_id,
                created_at=tenant.created_at,
            )
        )
        await self._session.flush()

    async def add_user(self, user: User) -> None:
        self._session.add(
            UserRow(
                id=user.id,
                tenant_id=user.tenant_id,
                email=user.email,
                password_hash=user.password_hash,
                email_verified_at=user.email_verified_at,
                created_at=user.created_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _EMAIL_UNIQUE_CONSTRAINT in str(error.orig):
                msg = "Email ya registrado."
                raise EmailAlreadyRegisteredError(msg) from None
            raise

    async def get_user_by_email(self, email: EmailAddress) -> User | None:
        row = await self._session.scalar(select(UserRow).where(UserRow.email == email.value))
        return None if row is None else _to_user(row)

    async def mark_email_verified(self, user_id: UserId, at: datetime) -> None:
        await self._session.execute(
            update(UserRow)
            .where(UserRow.id == user_id)
            .values(email_verified_at=func.coalesce(UserRow.email_verified_at, at))
        )

    async def add_email_verification(
        self, verification: EmailVerification, token_hash: str
    ) -> None:
        self._session.add(
            EmailVerificationRow(
                id=verification.id,
                user_id=verification.user_id,
                token_hash=token_hash,
                expires_at=verification.expires_at,
                used_at=verification.used_at,
            )
        )
        await self._session.flush()

    async def get_email_verification_for_update(self, token_hash: str) -> EmailVerification | None:
        row = await self._session.scalar(
            select(EmailVerificationRow)
            .where(EmailVerificationRow.token_hash == token_hash)
            .with_for_update()
        )
        if row is None:
            return None
        return EmailVerification(
            id=row.id, user_id=UserId(row.user_id), expires_at=row.expires_at, used_at=row.used_at
        )

    async def mark_email_verification_used(self, verification_id: UUID, at: datetime) -> None:
        await self._session.execute(
            update(EmailVerificationRow)
            .where(EmailVerificationRow.id == verification_id)
            .values(used_at=at)
        )

    async def add_session(self, session: Session, token_hash: str) -> None:
        self._session.add(
            SessionRow(
                id=session.id,
                user_id=session.user_id,
                token_hash=token_hash,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
            )
        )
        await self._session.flush()

    async def get_session_with_user(self, token_hash: str) -> tuple[Session, User] | None:
        result = await self._session.execute(
            select(SessionRow, UserRow)
            .join(UserRow, UserRow.id == SessionRow.user_id)
            .where(SessionRow.token_hash == token_hash)
        )
        found = result.first()
        if found is None:
            return None
        session_row, user_row = found
        return _to_session(session_row), _to_user(user_row)

    async def touch_session(self, session_id: SessionId, at: datetime) -> None:
        await self._session.execute(
            update(SessionRow).where(SessionRow.id == session_id).values(last_seen_at=at)
        )

    async def revoke_session(self, session_id: SessionId, at: datetime) -> None:
        await self._session.execute(
            update(SessionRow)
            .where(SessionRow.id == session_id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=at)
        )


def _to_user(row: UserRow) -> User:
    return User(
        id=UserId(row.id),
        tenant_id=TenantId(row.tenant_id),
        email=row.email,
        password_hash=row.password_hash,
        email_verified_at=row.email_verified_at,
        created_at=row.created_at,
    )


def _to_session(row: SessionRow) -> Session:
    return Session(
        id=SessionId(row.id),
        user_id=UserId(row.user_id),
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )
