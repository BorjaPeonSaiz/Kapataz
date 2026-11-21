"""tools/seed_demo.py contra PostgreSQL real, con el rol de la app (RF-CF-04, ADR-020).

La carga corre con ``kapataz_app`` (sin BYPASSRLS) y el espacio de
demostración fijado en la transacción. Las comprobaciones de lo escrito se
hacen con el propietario, que no queda filtrado por RLS, para ver también lo
que la app no vería.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import seed_demo
from kapataz.application.use_cases.account_creation import add_account
from kapataz.application.use_cases.admin.load_demo_space_for_account import (
    LoadDemoSpaceForAccount,
)
from kapataz.application.use_cases.load_demo_space import LoadDemoSpace
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import (
    AccountNotFoundError,
    DemoSpaceAlreadyExistsError,
    TenantAlreadyExistsError,
)
from kapataz.domain.accounts.model import (
    AuthenticatedUser,
    SessionId,
    Tenant,
    TenantId,
    demo_tenant_id,
)
from kapataz.domain.billing.ids import QuoteId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.customers.errors import DuplicateCustomerTaxIdError
from kapataz.domain.customers.model import CustomerId
from kapataz.domain.settings.professional import Professional
from kapataz.infrastructure.clock import FrozenClock
from synthetic.build import DEFAULT_SEED, build_dataset
from synthetic.model import SyntheticDataset, Trade
from tests.billing_support import ISSUER_TAX_ID, SEED_AT
from tests.integration import conftest as integration
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import run_sql
from tests.support import make_settings

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
DATASET: SyntheticDataset = build_dataset(DEFAULT_SEED)


# Tablas que llena la carga, con su columna de cuenta.
LOADED_TABLES = {
    "tenants": "id",
    "professional": "tenant_id",
    "customers": "tenant_id",
    "catalog_items": "tenant_id",
    "quotes": "tenant_id",
    "quote_versions": "tenant_id",
    "quote_lines": "tenant_id",
}


def _new_account(factory, *, with_professional: bool = True) -> tuple[str, TenantId]:
    """Cuenta normal con su usuario y, si se pide, sus datos de profesional."""
    email = f"demo-{uuid4().hex[:8]}@example.com"

    async def create() -> TenantId:
        async with factory() as uow:
            user_id = await add_account(
                uow, EmailAddress.parse(email), "hash", now=SEED_AT, verified=True
            )
            user = await uow.accounts.get_user_by_email(EmailAddress.parse(email))
            assert user is not None
            assert user.id == user_id
            if with_professional:
                await uow.professional.save(
                    Professional(
                        tenant_id=user.tenant_id,
                        name="Reformas Ejemplo",
                        tax_id=ISSUER_TAX_ID,
                        address="Calle Mayor 1, 28001 Madrid",
                        updated_at=SEED_AT,
                    )
                )
            await uow.commit()
            return user.tenant_id

    return email, asyncio.run(create())


def _seed(factory, account: str | TenantId, trade: Trade = Trade.ELECTRICIAN):
    return asyncio.run(seed_demo.seed_demo(factory, FrozenClock(NOW), account=account, trade=trade))


def _counts(database, role: str, tenant: UUID, *, as_tenant: UUID | None = None) -> dict[str, int]:
    """Filas de ``tenant`` en cada tabla, vistas por ``role`` con ``as_tenant`` fijada."""
    return {
        table: run_sql(
            database,
            role,
            f"SELECT count(*) FROM {table} WHERE {column} = :tenant",
            {"tenant": tenant},
            tenant_id=as_tenant,
        )[0][0]
        for table, column in LOADED_TABLES.items()
    }


def _all_rows(database) -> dict[str, int]:
    """Filas de cada tabla en toda la base de datos, vistas por el propietario."""
    return {
        table: run_sql(database, OWNER_ROLE, f"SELECT count(*) FROM {table}")[0][0]
        for table in LOADED_TABLES
    }


def _expected_counts(trade: Trade) -> dict[str, int]:
    data = DATASET.professional(trade)
    return {
        "tenants": 1,
        "professional": 1,
        "customers": len(data.customers),
        "catalog_items": len(data.catalog),
        "quotes": len(data.quotes),
        "quote_versions": len(data.quotes),
        "quote_lines": sum(len(quote.lines) for quote in data.quotes),
    }


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("trade", list(Trade))
def test_crea_el_espacio_con_su_padre_y_carga_todo_el_dataset(app_factory, database, trade):
    email, parent = _new_account(app_factory)

    loaded = _seed(app_factory, email, trade)

    demo = demo_tenant_id(parent)
    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (parent, demo)
    [row] = run_sql(
        database,
        OWNER_ROLE,
        "SELECT kind, parent_tenant_id, name, created_at FROM tenants WHERE id = :id",
        {"id": demo},
    )
    assert tuple(row) == ("demo", parent, None, NOW)
    expected = _expected_counts(trade)
    assert _counts(database, OWNER_ROLE, demo) == expected
    # La app, con el espacio fijado, lo ve entero.
    assert _counts(database, APP_ROLE, demo, as_tenant=demo) == expected
    data = DATASET.professional(trade)
    assert (loaded.customers, loaded.catalog_items, loaded.quotes) == (
        len(data.customers),
        len(data.catalog),
        len(data.quotes),
    )


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-03")
def test_la_base_de_cada_presupuesto_guardado_es_la_del_dataset(app_factory, database):
    email, parent = _new_account(app_factory)
    _seed(app_factory, email, Trade.BRICKLAYER)
    demo = demo_tenant_id(parent)
    stored = run_sql(
        database, APP_ROLE, "SELECT id, series, year, number FROM quotes", tenant_id=demo
    )
    numbers = {
        str(DocumentNumber(Series(series), year, number)): QuoteId(quote_id)
        for quote_id, series, year, number in stored
    }
    data = DATASET.professional(Trade.BRICKLAYER)
    assert set(numbers) == {quote.number for quote in data.quotes}

    async def bases() -> dict[str, Money]:
        async with app_factory() as uow:
            await uow.set_tenant(demo)
            found = {}
            for number, quote_id in numbers.items():
                quote = await uow.quotes.get(quote_id)
                assert quote is not None
                assert str(quote.number) == number
                found[number] = quote.current_version.base
            return found

    stored_bases = asyncio.run(bases())
    for quote in data.quotes:
        expected = sum((line.amount for line in quote.lines), Decimal("0.00"))
        assert stored_bases[quote.number] == Money(expected), quote.number


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-10")
@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_ni_la_cuenta_padre_ni_otra_ven_el_espacio_de_demostracion(app_factory, database):
    email, parent = _new_account(app_factory)
    _, other = _new_account(app_factory)
    _seed(app_factory, email)
    demo = demo_tenant_id(parent)
    nothing = dict.fromkeys(LOADED_TABLES, 0)

    # Con RLS, desde la cuenta padre, desde otra y sin cuenta fijada: ninguna fila.
    for as_tenant in (parent, other, None):
        assert _counts(database, APP_ROLE, demo, as_tenant=as_tenant) == nothing
    # Y nada se escribió fuera del espacio: la cuenta padre sigue como estaba.
    assert _counts(database, OWNER_ROLE, parent) == {**nothing, "tenants": 1, "professional": 1}
    [(name,)] = run_sql(
        database, OWNER_ROLE, "SELECT name FROM professional WHERE tenant_id = :t", {"t": parent}
    )
    assert name == "Reformas Ejemplo"

    # Un id del espacio, pedido desde la cuenta padre, no existe (la API respondería 404).
    [(quote_id,)] = run_sql(database, APP_ROLE, "SELECT id FROM quotes LIMIT 1", tenant_id=demo)
    [(customer_id,)] = run_sql(
        database, APP_ROLE, "SELECT id FROM customers LIMIT 1", tenant_id=demo
    )

    async def from_parent() -> tuple[object, ...]:
        async with app_factory() as uow:
            await uow.set_tenant(parent)
            return (
                await uow.quotes.get(QuoteId(quote_id)),
                await uow.customers.get(CustomerId(customer_id)),
                await uow.accounts.get_tenant(demo),
            )

    assert asyncio.run(from_parent()) == (None, None, None)


@pytest.mark.req("RF-CF-04")
def test_una_segunda_carga_falla_sin_escribir_nada(app_factory, database):
    email, parent = _new_account(app_factory)
    _seed(app_factory, email, Trade.ELECTRICIAN)
    before = _all_rows(database)

    with pytest.raises(DemoSpaceAlreadyExistsError, match="ya tiene un espacio"):
        _seed(app_factory, email, Trade.BRICKLAYER)

    assert _all_rows(database) == before
    assert _counts(database, OWNER_ROLE, demo_tenant_id(parent)) == _expected_counts(
        Trade.ELECTRICIAN
    )


@pytest.mark.req("RF-CF-04")
def test_dos_cargas_a_la_vez_solo_una_crea_el_espacio(app_factory, database):
    email, parent = _new_account(app_factory)
    before = _all_rows(database)

    async def both() -> list[object]:
        return await asyncio.gather(
            *(
                seed_demo.seed_demo(app_factory, FrozenClock(NOW), account=email, trade=trade)
                for trade in Trade
            ),
            return_exceptions=True,
        )

    results = asyncio.run(both())

    failed = [r for r in results if isinstance(r, BaseException)]
    assert len(failed) == 1
    assert isinstance(failed[0], DemoSpaceAlreadyExistsError)
    after = _all_rows(database)
    assert after["tenants"] == before["tenants"] + 1
    winner = Trade.ELECTRICIAN if failed[0] is results[1] else Trade.BRICKLAYER
    assert _counts(database, OWNER_ROLE, demo_tenant_id(parent)) == _expected_counts(winner)


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("other_id", [False, True])
def test_la_base_de_datos_impide_dar_de_alta_dos_espacios_de_una_cuenta(app_factory, other_id):
    """Con el mismo id lo para la clave primaria; con otro, el índice único (0004)."""
    _, parent_id = _new_account(app_factory)

    async def add_twice() -> None:
        async with app_factory() as uow:
            await uow.set_tenant(parent_id)
            parent = await uow.accounts.get_tenant(parent_id)
            assert parent is not None
            demo = Tenant.demo_of(parent, NOW)
            await uow.accounts.add_tenant(demo)
            twin = replace(demo, id=TenantId(uuid4())) if other_id else demo
            await uow.accounts.add_tenant(replace(twin, created_at=SEED_AT))

    with pytest.raises(TenantAlreadyExistsError):
        asyncio.run(add_twice())


@pytest.mark.req("RF-CF-04")
def test_una_cuenta_inexistente_da_un_error_claro_sin_escribir_nada(app_factory, database):
    before = _all_rows(database)
    with pytest.raises(AccountNotFoundError, match="No hay ninguna cuenta con ese email"):
        _seed(app_factory, f"nadie-{uuid4().hex[:8]}@example.com")
    with pytest.raises(AccountNotFoundError, match="La cuenta no existe"):
        _seed(app_factory, TenantId(uuid4()))
    assert _all_rows(database) == before


@pytest.mark.req("RF-CF-04")
def test_si_algo_falla_a_mitad_no_queda_ni_el_espacio(app_factory, database):
    email, parent = _new_account(app_factory)
    before = _all_rows(database)
    data = DATASET.professional(Trade.ELECTRICIAN)

    def broken(tenant_id: TenantId):
        content = seed_demo.demo_content(data, tenant_id, since=DATASET.period_start)
        twin = replace(content.customers[-1], id=CustomerId(uuid4()))
        return replace(content, customers=(*content.customers, twin))

    use_case = LoadDemoSpaceForAccount(app_factory, FrozenClock(NOW))
    with pytest.raises(DuplicateCustomerTaxIdError):
        asyncio.run(use_case.execute(email, broken))

    assert _all_rows(database) == before
    assert _counts(database, OWNER_ROLE, demo_tenant_id(parent)) == dict.fromkeys(LOADED_TABLES, 0)


@pytest.mark.req("RF-CF-04")
def test_desde_el_id_de_la_cuenta_carga_lo_mismo(app_factory, database):
    _, parent = _new_account(app_factory)

    loaded = _seed(app_factory, parent, Trade.BRICKLAYER)

    assert loaded.demo_tenant_id == demo_tenant_id(parent)
    assert _counts(database, OWNER_ROLE, loaded.demo_tenant_id) == _expected_counts(
        Trade.BRICKLAYER
    )


def _session_user(factory, email: str) -> AuthenticatedUser:
    """El usuario de la sesión de la cuenta de ``email``, como lo deja AuthenticateSession."""

    async def find() -> AuthenticatedUser:
        async with factory() as uow:
            user = await uow.accounts.get_user_by_email(EmailAddress.parse(email))
        assert user is not None
        return AuthenticatedUser(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            session_id=SessionId(uuid4()),
        )

    return asyncio.run(find())


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_desde_la_sesion_carga_el_espacio_de_la_cuenta_del_usuario(app_factory, database):
    """S3-R-03: la cuenta sale del usuario autenticado; la otra cuenta no cambia."""
    email, parent = _new_account(app_factory)
    _, other = _new_account(app_factory)
    other_before = _counts(database, OWNER_ROLE, demo_tenant_id(other))
    data = DATASET.professional(Trade.ELECTRICIAN)
    build = seed_demo.content_builder(data, since=DATASET.period_start)

    use_case = LoadDemoSpace(app_factory, FrozenClock(NOW))
    loaded = asyncio.run(use_case.execute(_session_user(app_factory, email), build))

    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (parent, demo_tenant_id(parent))
    assert _counts(database, OWNER_ROLE, loaded.demo_tenant_id) == _expected_counts(
        Trade.ELECTRICIAN
    )
    assert _counts(database, OWNER_ROLE, demo_tenant_id(other)) == other_before


@pytest.mark.req("RF-CF-04")
def test_los_presupuestos_facturados_entran_como_aceptados(app_factory, database):
    """I-4: el espacio no tiene las facturas de sus presupuestos."""
    _, parent = _new_account(app_factory)
    _seed(app_factory, parent, Trade.ELECTRICIAN)
    demo = demo_tenant_id(parent)
    rows = run_sql(
        database, APP_ROLE, "SELECT series, year, number, status FROM quotes", tenant_id=demo
    )
    stored = {
        str(DocumentNumber(Series(series), year, number)): status
        for series, year, number, status in rows
    }

    expected = {
        quote.number: seed_demo.demo_status(quote.status).value
        for quote in DATASET.professional(Trade.ELECTRICIAN).quotes
    }
    assert stored == expected
    assert not {"invoiced", "partially_invoiced"} & set(stored.values())


# ------------------------------------------------------------------ la orden


def _point_main_at(
    monkeypatch, database: integration.TestDatabase, role: str, *, db_name: str | None = None
) -> None:
    """``main`` conecta con ``role`` (y otra base de datos, si se da) en vez de con DATABASE_URL."""

    def open_database(_settings):
        if db_name is None:
            return seed_demo.SqlDatabase(database.engine(role))
        url = database.urls[role].set(database=db_name)
        return seed_demo.SqlDatabase(create_async_engine(url, poolclass=NullPool))

    monkeypatch.setattr(seed_demo, "open_database", open_database)
    monkeypatch.setattr(seed_demo, "Settings", make_settings)
    monkeypatch.setattr(seed_demo, "configure_logging", lambda: None)


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RNF-13")
def test_con_el_rol_de_la_app_la_orden_carga(monkeypatch, app_factory, database, capsys):
    _, parent = _new_account(app_factory)
    _point_main_at(monkeypatch, database, APP_ROLE)

    code = seed_demo.main(["--account-id", str(parent), "--trade", "albanil"])

    assert code == seed_demo.EXIT_OK, capsys.readouterr().err
    assert _counts(database, OWNER_ROLE, demo_tenant_id(parent)) == _expected_counts(
        Trade.BRICKLAYER
    )


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_con_el_propietario_la_orden_se_niega_sin_escribir(
    monkeypatch, app_factory, database, capsys
):
    """S3-07: el propietario se salta RLS (tenants no tiene FORCE)."""
    _, parent = _new_account(app_factory)
    before = _all_rows(database)
    _point_main_at(monkeypatch, database, OWNER_ROLE)

    code = seed_demo.main(["--account-id", str(parent), "--trade", "albanil"])

    assert code == seed_demo.EXIT_ERROR
    err = capsys.readouterr().err
    assert "propietario de las tablas" in err
    assert "kapataz_app" in err
    assert _all_rows(database) == before


@pytest.mark.req("RNF-13")
def test_el_rol_de_la_app_es_seguro_y_el_propietario_no(database):
    async def role(name: str) -> seed_demo.ConnectedRole:
        db = seed_demo.SqlDatabase(database.engine(name))
        try:
            return await db.connected_role()
        finally:
            await db.dispose()

    assert asyncio.run(role(APP_ROLE)).unsafe_reasons() == []
    assert asyncio.run(role(OWNER_ROLE)) == seed_demo.ConnectedRole(
        superuser=False, bypass_rls=False, table_owner=True
    )


@pytest.mark.req("RF-CF-04")
def test_un_error_de_postgresql_al_conectar_sale_con_el_mensaje_fijo(monkeypatch, database, capsys):
    """S3-08: asyncpg rechaza la base de datos al conectar, sin que SQLAlchemy lo envuelva."""
    missing = f"no_existe_{uuid4().hex[:8]}"
    _point_main_at(monkeypatch, database, APP_ROLE, db_name=missing)

    code = seed_demo.main(["--account-id", str(uuid4()), "--trade", "albanil"])

    assert code == seed_demo.EXIT_ERROR
    err = capsys.readouterr().err
    assert err == seed_demo.DATABASE_FAILED
    assert missing not in err
