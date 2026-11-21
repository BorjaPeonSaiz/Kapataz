"""Unidad de trabajo y repositorios (ADR-001, ADR-024)."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from kapataz.application.ports.repositories import (
    BillingChainRepository,
    CatalogRepository,
    CustomerRepository,
    InvoiceRepository,
    PaymentRepository,
    ProfessionalRepository,
    QuoteRepository,
    SeriesCounterRepository,
)
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.model import (
    EmailVerification,
    Session,
    SessionId,
    Tenant,
    TenantId,
    User,
    UserId,
)


class AccountRepository(Protocol):
    """Repositorio de cuentas acotado.

    Es el único que lee las tablas globales sin RLS (``users``, ``sessions``,
    ``email_verifications``), porque se consultan antes de saber de qué cuenta
    se trata: al iniciar sesión o al validar la cookie (ADR-024).
    """

    async def add_tenant(self, tenant: Tenant) -> None:
        """Requiere la cuenta fijada en la transacción: ``tenants`` tiene RLS.

        Una cuenta normal se da de alta con ella misma fijada; un espacio de
        demostración, con su cuenta padre fijada (migración 0004).

        Lanza ``TenantAlreadyExistsError`` si ya hay una cuenta con ese id o la
        cuenta padre ya tiene espacio de demostración.
        """
        ...

    async def get_tenant(self, tenant_id: TenantId) -> Tenant | None:
        """La cuenta, si es la fijada en la transacción; si no, None (RLS)."""
        ...

    async def add_user(self, user: User) -> None:
        """Lanza ``EmailAlreadyRegisteredError`` si el email ya existe."""
        ...

    async def get_user_by_email(self, email: EmailAddress) -> User | None: ...

    async def mark_email_verified(self, user_id: UserId, at: datetime) -> None: ...

    async def add_email_verification(
        self, verification: EmailVerification, token_hash: str
    ) -> None: ...

    async def get_email_verification_for_update(self, token_hash: str) -> EmailVerification | None:
        """Bloquea la fila: dos peticiones con el mismo enlace no lo usan dos veces."""
        ...

    async def mark_email_verification_used(self, verification_id: UUID, at: datetime) -> None: ...

    async def add_session(self, session: Session, token_hash: str) -> None: ...

    async def get_session_with_user(self, token_hash: str) -> tuple[Session, User] | None: ...

    async def touch_session(self, session_id: SessionId, at: datetime) -> None: ...

    async def revoke_session(self, session_id: SessionId, at: datetime) -> None: ...


class UnitOfWork(Protocol):
    """Una transacción. Sin ``commit()`` explícito, todo se deshace al salir.

    Los repositorios de negocio trabajan en la cuenta fijada con ``set_tenant``
    (``repositories``).
    """

    @property
    def accounts(self) -> AccountRepository: ...

    @property
    def professional(self) -> ProfessionalRepository: ...

    @property
    def customers(self) -> CustomerRepository: ...

    @property
    def catalog(self) -> CatalogRepository: ...

    @property
    def quotes(self) -> QuoteRepository: ...

    @property
    def invoices(self) -> InvoiceRepository: ...

    @property
    def payments(self) -> PaymentRepository: ...

    @property
    def series_counters(self) -> SeriesCounterRepository: ...

    @property
    def billing_chain(self) -> BillingChainRepository: ...

    async def set_tenant(self, tenant_id: TenantId) -> None:
        """Fija la cuenta solo para esta transacción (``SET LOCAL``, ADR-024)."""
        ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[UnitOfWork]: ...


class DatabaseProbe(Protocol):
    async def ping(self) -> bool:
        """``True`` si la base de datos responde; nunca lanza."""
        ...
