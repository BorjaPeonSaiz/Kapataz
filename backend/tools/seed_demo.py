"""Carga el modo demostración de una cuenta con un profesional sintético (RF-CF-04, ADR-020).

Uso, desde ``backend/``::

    uv run python tools/seed_demo.py --account ana@example.com --trade electricista
    uv run python tools/seed_demo.py --account-id <uuid de la cuenta> --trade albanil --seed 7

La cuenta se elige por el email de su usuario (``--account``) o por su id
(``--account-id``), uno de los dos. El id evita dejar un email en el historial
de la consola.

Crea el espacio de demostración de la cuenta (``tenants.kind = 'demo'``, con
``parent_tenant_id`` apuntando a ella) y carga en él, con el dominio y los
repositorios de la app, el profesional, sus clientes, su catálogo y sus
presupuestos, tal como los produce ``synthetic.build.build_dataset(seed)``.
No emite facturas: el histórico llega como documentos importados (Bloque 4).

- Se conecta con ``DATABASE_URL``, que tiene que ser el rol de la app
  (``kapataz_app``): cada escritura pasa por RLS con la cuenta fijada en la
  transacción, así que nada puede caer en otra cuenta. Antes de cargar nada
  comprueba el rol conectado y se niega si es superusuario, tiene BYPASSRLS o
  tiene los privilegios del propietario de las tablas: con él, RLS no filtra.
- Una sola transacción: o se carga todo o nada.
- Si la cuenta ya tiene espacio de demostración, falla sin escribir nada.
- Solo muestra ids y conteos: ni nombres ni NIF, aunque sean sintéticos
  (ADR-015). Un error de base de datos sale con un mensaje fijo, sin traza ni
  ``DETAIL``, que podrían llevar datos.

Códigos de salida:

- 0: espacio creado y cargado;
- 1: la cuenta no existe, ya tiene espacio, el email no es válido, el rol
  conectado no es seguro (superusuario, BYPASSRLS o propietario), la
  configuración no es válida, o ha fallado la base de datos o la conexión;
- 2: los argumentos no son válidos (los rechaza ``argparse``).
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as day_time
from functools import partial
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import asyncpg
import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from kapataz.application.ports.persistence import UnitOfWorkFactory
from kapataz.application.use_cases.admin.load_demo_space_for_account import (
    LoadDemoSpaceForAccount,
)
from kapataz.application.use_cases.admin.load_demo_space_for_account_id import (
    LoadDemoSpaceForAccountId,
)
from kapataz.application.use_cases.demo_space import (
    DemoContent,
    DemoContentBuilder,
    LoadedDemoSpace,
)
from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.ids import QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage, Quantity
from kapataz.domain.billing.quote import (
    PriceSource,
    PriceSourceKind,
    Quote,
    QuoteLine,
    QuoteStatus,
    QuoteVersion,
)
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from kapataz.domain.clock import Clock
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.customers.tax_id import TaxId
from kapataz.domain.errors import DomainError
from kapataz.domain.settings.professional import Professional
from kapataz.infrastructure.clock import SystemClock
from kapataz.infrastructure.logging.setup import configure_logging
from kapataz.infrastructure.persistence.database import create_engine
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from kapataz.infrastructure.settings import Settings
from synthetic.build import DEFAULT_SEED, build_dataset
from synthetic.model import CatalogEntryData, LineData, ProfessionalDataset, QuoteData, Trade

EXIT_OK = 0
EXIT_ERROR = 1

FAILED = "No se han cargado los datos de ejemplo"
DATABASE_FAILED = (
    f"{FAILED}: ha fallado la base de datos o la conexión. Revisa DATABASE_URL y que "
    "PostgreSQL esté en marcha.\n"
)

# Errores de base de datos o de conexión. asyncpg puede lanzar los suyos sin
# envolver al conectar; OSError cubre la conexión rechazada y el tiempo agotado.
_DATABASE_ERRORS = (SQLAlchemyError, asyncpg.PostgresError, asyncpg.InterfaceError, OSError)

# Las fechas del dataset son días; la hora de alta es las 9:00 en España.
_TIMEZONE = ZoneInfo("Europe/Madrid")
_START_OF_DAY = day_time(9)

# El espacio no tiene las facturas de sus presupuestos (el histórico llega
# como documentos importados, Bloque 4): uno facturado, del todo o en parte,
# entra como aceptado, que es lo que era antes de facturarse. Decisión de
# Borja (I-4); el dataset del generador no cambia.
_WITHOUT_INVOICES = {
    QuoteStatus.INVOICED: QuoteStatus.ACCEPTED,
    QuoteStatus.PARTIALLY_INVOICED: QuoteStatus.ACCEPTED,
}

_log = structlog.get_logger("seed_demo")


def _at(day: date) -> datetime:
    return datetime.combine(day, _START_OF_DAY, tzinfo=_TIMEZONE)


def _catalog_item(
    entry: CatalogEntryData, tenant_id: TenantId, created_at: datetime
) -> CatalogItem:
    return CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept=entry.concept,
        unit=entry.unit,
        reference_price=Money(entry.reference_price),
        origin=CatalogItemOrigin.MANUAL,
        is_material=entry.is_material,
        created_at=created_at,
    )


def _price_source(line: LineData, catalog: dict[str, CatalogItem]) -> PriceSource:
    """Una línea que sale de un concepto del catálogo lo cita (RN-06); las demás, a mano."""
    if line.catalog_key is None:
        return PriceSource.manual()
    return PriceSource(kind=PriceSourceKind.CATALOG, reference_id=catalog[line.catalog_key].id)


def demo_status(status: QuoteStatus) -> QuoteStatus:
    """Estado con el que entra en el espacio un presupuesto del dataset."""
    return _WITHOUT_INVOICES.get(status, status)


def _quote(
    data: QuoteData,
    tenant_id: TenantId,
    customers: dict[str, Customer],
    catalog: dict[str, CatalogItem],
) -> Quote:
    lines = tuple(
        QuoteLine(
            id=QuoteLineId(uuid4()),
            description=line.description,
            quantity=Quantity(line.quantity),
            unit_price=Money(line.unit_price),
            price_source=_price_source(line, catalog),
            discount=None if line.discount is None else Percentage(line.discount),
            is_material=line.is_material,
            outside_works=line.outside_works,
        )
        for line in data.lines
    )
    created_at = _at(data.issue_date)
    version = QuoteVersion(
        id=QuoteVersionId(uuid4()),
        version=1,
        lines=lines,
        recipient_type=data.recipient_type,
        dwelling_over_two_years=data.dwelling_over_two_years,
        valid_until=data.valid_until,
        created_at=created_at,
    )
    return Quote(
        id=QuoteId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customers[data.customer_key].id,
        number=DocumentNumber.parse(data.number),
        status=demo_status(data.status),
        versions=(version,),
        created_at=created_at,
    )


def demo_content(data: ProfessionalDataset, tenant_id: TenantId, *, since: date) -> DemoContent:
    """Paso del dataset sintético al dominio, en la cuenta ``tenant_id``.

    Las fechas salen del dataset: el profesional y su catálogo, del primer día
    de actividad (``since``); cada cliente, de su alta; cada presupuesto, de su
    fecha.
    """
    started = _at(since)
    pro = data.professional
    professional = Professional(
        tenant_id=tenant_id,
        name=pro.name,
        tax_id=TaxId(pro.tax_id),
        address=pro.address,
        updated_at=started,
    )
    customers = {
        customer.key: Customer(
            id=CustomerId(uuid4()),
            tenant_id=tenant_id,
            name=customer.name,
            tax_id=TaxId(customer.tax_id),
            address=customer.address,
            created_at=_at(customer.since),
        )
        for customer in data.customers
    }
    catalog = {entry.key: _catalog_item(entry, tenant_id, started) for entry in data.catalog}
    quotes = tuple(_quote(quote, tenant_id, customers, catalog) for quote in data.quotes)
    return DemoContent(
        professional=professional,
        customers=tuple(customers.values()),
        catalog=tuple(catalog.values()),
        quotes=quotes,
    )


def content_builder(data: ProfessionalDataset, *, since: date) -> DemoContentBuilder:
    return partial(demo_content, data, since=since)


async def seed_demo(
    uow_factory: UnitOfWorkFactory,
    clock: Clock,
    *,
    account: str | TenantId,
    trade: Trade,
    seed: int = DEFAULT_SEED,
) -> LoadedDemoSpace:
    """Crea y llena el espacio de la cuenta (su email o su id), en una transacción.

    El dataset se genera antes de abrir la transacción, para que dure poco.
    """
    dataset = build_dataset(seed)
    build = content_builder(dataset.professional(trade), since=dataset.period_start)
    if isinstance(account, UUID):
        return await LoadDemoSpaceForAccountId(uow_factory, clock).execute(account, build)
    return await LoadDemoSpaceForAccount(uow_factory, clock).execute(account, build)


# ------------------------------------------------------------ base de datos


@dataclass(frozen=True, slots=True)
class ConnectedRole:
    """Atributos del rol conectado que harían que RLS no filtrase."""

    superuser: bool
    bypass_rls: bool
    table_owner: bool

    def unsafe_reasons(self) -> list[str]:
        flags = (
            (self.superuser, "es superusuario"),
            (self.bypass_rls, "tiene BYPASSRLS"),
            (self.table_owner, "tiene los privilegios del propietario de las tablas"),
        )
        return [reason for flag, reason in flags if flag]


class UnsafeRoleError(Exception):
    """El rol conectado se saltaría RLS: la carga no garantizaría el aislamiento."""


# Como tests/integration/test_rls.py, y un poco más: el propietario se salta
# RLS (tenants no tiene FORCE), y también quien hereda sus privilegios. Con
# pg_has_role(…, 'USAGE') cuenta el propio propietario y cualquier miembro suyo
# con INHERIT.
_ROLE_QUERY = text(
    "SELECT r.rolsuper, r.rolbypassrls, EXISTS ("
    "SELECT 1 FROM pg_catalog.pg_tables t WHERE t.schemaname = 'public' "
    "AND pg_catalog.pg_has_role(current_user, t.tableowner, 'USAGE')) "
    "FROM pg_catalog.pg_roles r WHERE r.rolname = current_user"
)


class Database(Protocol):
    @property
    def uow_factory(self) -> UnitOfWorkFactory: ...

    async def connected_role(self) -> ConnectedRole: ...

    async def dispose(self) -> None: ...


class SqlDatabase:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._uow_factory = SqlAlchemyUnitOfWorkFactory(engine)

    @property
    def uow_factory(self) -> UnitOfWorkFactory:
        return self._uow_factory

    async def connected_role(self) -> ConnectedRole:
        async with self._engine.connect() as conn:
            superuser, bypass_rls, table_owner = (await conn.execute(_ROLE_QUERY)).one()
        return ConnectedRole(bool(superuser), bool(bypass_rls), bool(table_owner))

    async def dispose(self) -> None:
        await self._engine.dispose()


def open_database(settings: Settings) -> Database:
    """Motor con ``DATABASE_URL`` y su unidad de trabajo.

    Las pruebas lo sustituyen para conectar con su base de datos desechable.
    """
    return SqlDatabase(create_engine(settings.database_url, pool_size=1, max_overflow=0))


async def check_role(database: Database) -> None:
    """Falla si el rol conectado se saltaría RLS (S3-07)."""
    reasons = (await database.connected_role()).unsafe_reasons()
    if reasons:
        msg = (
            f"el rol conectado {', '.join(reasons)}, así que RLS no lo filtraría. "
            "Usa en DATABASE_URL el rol de la app (kapataz_app)."
        )
        raise UnsafeRoleError(msg)


async def _run(
    settings: Settings, account: str | TenantId, trade: Trade, seed: int
) -> LoadedDemoSpace:
    database = open_database(settings)
    try:
        await check_role(database)
        return await seed_demo(
            database.uow_factory, SystemClock(), account=account, trade=trade, seed=seed
        )
    finally:
        await database.dispose()


# ------------------------------------------------------------------ la orden


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_demo",
        description="Carga datos de ejemplo en el espacio de demostración de una cuenta.",
    )
    account = parser.add_mutually_exclusive_group(required=True)
    account.add_argument("--account", help="email del usuario de una cuenta existente")
    account.add_argument("--account-id", type=UUID, help="id de una cuenta existente")
    parser.add_argument(
        "--trade", required=True, choices=[trade.value for trade in Trade], help="profesional"
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="semilla (por defecto, la de samples/)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configure_logging()
    trade = Trade(args.trade)
    account: str | TenantId = args.account if args.account_id is None else TenantId(args.account_id)
    started = time.perf_counter()
    try:
        loaded = asyncio.run(_run(Settings(), account, trade, args.seed))
    except _DATABASE_ERRORS as error:
        # Antes que ValueError: algún error de asyncpg también lo es. El texto
        # de PostgreSQL puede llevar valores en DETAIL: solo se apunta el tipo.
        _log.warning(
            "demo_space_failed", use_case="load_demo_space", error_type=type(error).__name__
        )
        sys.stderr.write(DATABASE_FAILED)
        return EXIT_ERROR
    except (DomainError, ValueError, UnsafeRoleError) as error:
        # Ni los errores del dominio, ni los de configuración (hide_input_in_errors),
        # ni el del rol llevan en el mensaje el email u otros datos.
        sys.stderr.write(f"{FAILED}: {error}\n")
        return EXIT_ERROR
    duration_ms = round((time.perf_counter() - started) * 1000)
    _log.info(
        "demo_space_loaded",
        use_case="load_demo_space",
        tenant_id=str(loaded.parent_tenant_id),
        demo_tenant_id=str(loaded.demo_tenant_id),
        trade=trade.value,
        seed=args.seed,
        customers=loaded.customers,
        catalog_items=loaded.catalog_items,
        quotes=loaded.quotes,
        duration_ms=duration_ms,
    )
    sys.stdout.write(
        f"Espacio de demostración creado. demo_tenant_id={loaded.demo_tenant_id} "
        f"profesional=1 clientes={loaded.customers} catalogo={loaded.catalog_items} "
        f"presupuestos={loaded.quotes}\n"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
