"""Núcleo de la carga del espacio de demostración (RF-CF-04), común a sus tres entradas.

Crea y llena el espacio de la cuenta que recibe, sea cual sea. Por eso la API
no lo importa (contrato de import-linter en ``pyproject.toml``, S3-R-03): allí
la única entrada es ``LoadDemoSpace``, que toma la cuenta del usuario
autenticado. Las que eligen la cuenta por id o por email son de administración
(``admin/``).

El espacio es una cuenta aparte (``tenants.kind = 'demo'``) que apunta a la
cuenta con ``parent_tenant_id``. Su fila de ``tenants`` se da de alta con la
cuenta padre fijada en la transacción: la base de datos solo deja crear el
espacio de la cuenta fijada (migración 0004). El contenido se escribe después
con el espacio fijado: RLS impide que una fila caiga en la cuenta padre o en
otra (ADR-024).

Si la cuenta ya tiene espacio, falla sin escribir nada: vaciarlo o sustituirlo
es la función de mantenimiento (arquitectura §5.4).
"""

from datetime import datetime

from kapataz.application.ports.persistence import UnitOfWork
from kapataz.application.use_cases.demo_space import DemoContentBuilder, LoadedDemoSpace
from kapataz.domain.accounts.errors import (
    AccountNotFoundError,
    DemoSpaceAlreadyExistsError,
    TenantAlreadyExistsError,
)
from kapataz.domain.accounts.model import Tenant, TenantId


async def load_demo_space(
    uow: UnitOfWork, parent_tenant_id: TenantId, build: DemoContentBuilder, *, now: datetime
) -> LoadedDemoSpace:
    """Crea y llena el espacio en la transacción de ``uow``; quien llama confirma."""
    await uow.set_tenant(parent_tenant_id)
    parent = await uow.accounts.get_tenant(parent_tenant_id)
    if parent is None:
        raise AccountNotFoundError("La cuenta no existe.")
    demo = Tenant.demo_of(parent, now)
    # El alta, con la cuenta padre fijada. La clave primaria (id derivado) y el
    # índice único de la cuenta padre deciden si ya tenía espacio, también si
    # otra carga del mismo espacio ha llegado a la vez y ha ganado.
    try:
        await uow.accounts.add_tenant(demo)
    except TenantAlreadyExistsError:
        raise DemoSpaceAlreadyExistsError(
            "La cuenta ya tiene un espacio de demostración. Vaciarlo o sustituirlo es tarea "
            "de la función de mantenimiento."
        ) from None
    # Desde aquí, todo en el espacio de demostración.
    await uow.set_tenant(demo.id)
    content = build(demo.id)
    await uow.professional.save(content.professional)
    for customer in content.customers:
        await uow.customers.add(customer)
    for item in content.catalog:
        await uow.catalog.add(item)
    for quote in content.quotes:
        await uow.quotes.add(quote)
    return LoadedDemoSpace(
        parent_tenant_id=parent.id,
        demo_tenant_id=demo.id,
        customers=len(content.customers),
        catalog_items=len(content.catalog),
        quotes=len(content.quotes),
    )
