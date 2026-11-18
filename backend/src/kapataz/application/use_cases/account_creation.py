"""Alta de una cuenta con su primer usuario, común al registro y a la cortesía."""

from datetime import datetime
from uuid import uuid4

from kapataz.application.ports.persistence import UnitOfWork
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.model import Tenant, TenantId, TenantKind, User, UserId


async def add_account(
    uow: UnitOfWork,
    email: EmailAddress,
    password_hash: str,
    *,
    now: datetime,
    verified: bool,
) -> UserId:
    """Crea una cuenta normal y su usuario en la unidad de trabajo, sin confirmarla.

    La cuenta nace sin nombre: el email es un dato personal del usuario y no se
    copia en ``tenants``. El nombre llega con los datos del profesional.
    """
    tenant_id = TenantId(uuid4())
    await uow.set_tenant(tenant_id)
    await uow.accounts.add_tenant(
        Tenant(
            id=tenant_id,
            name=None,
            kind=TenantKind.STANDARD,
            parent_tenant_id=None,
            created_at=now,
        )
    )
    user_id = UserId(uuid4())
    await uow.accounts.add_user(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=email.value,
            password_hash=password_hash,
            email_verified_at=now if verified else None,
            created_at=now,
        )
    )
    return user_id
