"""Contenido y resultado de la carga del espacio de demostración (RF-CF-04).

Los comparten las tres entradas de la carga: la de la cuenta de la sesión
(``LoadDemoSpace``) y las de administración, por id y por email
(``admin/``). El núcleo que escribe está en ``demo_space_loader``.
"""

from collections.abc import Callable
from dataclasses import dataclass

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.quote import Quote
from kapataz.domain.catalog.model import CatalogItem
from kapataz.domain.customers.model import Customer
from kapataz.domain.settings.professional import Professional


@dataclass(frozen=True, slots=True, kw_only=True)
class DemoContent:
    """Datos de ejemplo de un profesional, todos de la cuenta del espacio de demostración."""

    professional: Professional
    customers: tuple[Customer, ...]
    catalog: tuple[CatalogItem, ...]
    quotes: tuple[Quote, ...]


# Recibe el id del espacio de demostración y devuelve su contenido.
type DemoContentBuilder = Callable[[TenantId], DemoContent]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadedDemoSpace:
    """Qué se ha cargado: ids y conteos, sin datos personales (ADR-015)."""

    parent_tenant_id: TenantId
    demo_tenant_id: TenantId
    customers: int
    catalog_items: int
    quotes: int
