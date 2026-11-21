"""tools/seed_demo.py sin PostgreSQL: paso del dataset al dominio y la orden (RF-CF-04).

La carga real, con RLS, está en ``tests/integration/persistence/test_seed_demo.py``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

import seed_demo
from kapataz.application.use_cases.account_creation import add_account
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.model import TenantId, demo_tenant_id
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.quote import PriceSourceKind, QuoteStatus
from synthetic.model import Trade
from tests.fakes.memory_uow import MemoryUnitOfWorkFactory
from tests.support import make_settings

if TYPE_CHECKING:
    from synthetic.model import SyntheticDataset

EMAIL = "demo@example.com"
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
# Un valor que no puede aparecer en lo que muestra la orden.
SECRET = "12345678Z"


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("trade", list(Trade))
def test_el_contenido_sale_del_dataset_en_la_cuenta_dada(dataset: SyntheticDataset, trade):
    data = dataset.professional(trade)
    tenant_id = TenantId(uuid4())

    content = seed_demo.demo_content(data, tenant_id, since=dataset.period_start)

    assert content.professional.name == data.professional.name
    assert str(content.professional.tax_id) == data.professional.tax_id
    assert len(content.customers) == len(data.customers)
    assert len(content.catalog) == len(data.catalog)
    assert len(content.quotes) == len(data.quotes)
    entities = (*content.customers, *content.catalog, *content.quotes)
    assert {entity.tenant_id for entity in (content.professional, *entities)} == {tenant_id}
    assert all(entity.created_at.tzinfo is not None for entity in entities)
    catalog_ids = {item.id for item in content.catalog}
    customer_ids = {customer.id for customer in content.customers}
    for expected, quote in zip(data.quotes, content.quotes, strict=True):
        assert str(quote.number) == expected.number
        assert quote.status is seed_demo.demo_status(expected.status)
        assert quote.customer_id in customer_ids
        assert quote.created_at.date() == expected.issue_date
        version = quote.current_version
        base = sum((line.amount for line in expected.lines), Decimal("0.00"))
        assert version.base == Money(base)
        assert version.recipient_type is expected.recipient_type
        assert version.valid_until == expected.valid_until
        for line, source in zip(expected.lines, version.lines, strict=True):
            if line.catalog_key is None:
                assert source.price_source.kind is PriceSourceKind.MANUAL
            else:
                assert source.price_source.kind is PriceSourceKind.CATALOG
                assert source.price_source.reference_id in catalog_ids


@pytest.mark.req("RF-CF-04")
def test_un_presupuesto_facturado_entra_como_aceptado():
    """I-4: el espacio no tiene las facturas; los demás estados no cambian."""
    invoiced = {QuoteStatus.INVOICED, QuoteStatus.PARTIALLY_INVOICED}
    for status in QuoteStatus:
        expected = QuoteStatus.ACCEPTED if status in invoiced else status
        assert seed_demo.demo_status(status) is expected


@pytest.mark.req("RF-CF-04")
def test_el_dataset_tiene_facturados_y_ninguno_entra_como_facturado(dataset: SyntheticDataset):
    invoiced = {QuoteStatus.INVOICED, QuoteStatus.PARTIALLY_INVOICED}
    statuses: set[QuoteStatus] = set()
    for trade in Trade:
        data = dataset.professional(trade)
        content = seed_demo.demo_content(data, TenantId(uuid4()), since=dataset.period_start)
        assert not invoiced & {quote.status for quote in content.quotes}
        statuses |= {quote.status for quote in data.quotes}
    # Si el generador dejara de producirlos, la prueba anterior no probaría nada.
    assert invoiced & statuses


# ------------------------------------------------------------------ la orden


class FakeDatabase:
    """Base de datos de la orden: la unidad de trabajo en memoria y el rol que se diga."""

    def __init__(self, factory: MemoryUnitOfWorkFactory) -> None:
        self.factory = factory
        self.role = seed_demo.ConnectedRole(superuser=False, bypass_rls=False, table_owner=False)
        self.role_error: BaseException | None = None
        self.disposed = 0

    @property
    def uow_factory(self) -> MemoryUnitOfWorkFactory:
        return self.factory

    async def connected_role(self) -> seed_demo.ConnectedRole:
        if self.role_error is not None:
            raise self.role_error
        return self.role

    async def dispose(self) -> None:
        self.disposed += 1


@pytest.fixture
def fake_db(monkeypatch) -> FakeDatabase:
    """La orden con la unidad de trabajo en memoria y una cuenta con ``EMAIL``."""
    factory = MemoryUnitOfWorkFactory()

    async def create() -> None:
        async with factory() as uow:
            await add_account(uow, EmailAddress.parse(EMAIL), "hash", now=NOW, verified=True)
            await uow.commit()

    asyncio.run(create())
    database = FakeDatabase(factory)
    monkeypatch.setattr(seed_demo, "open_database", lambda _settings: database)
    monkeypatch.setattr(seed_demo, "Settings", make_settings)
    # Los logs los configura ``captured_logs`` cuando la prueba los lee.
    monkeypatch.setattr(seed_demo, "configure_logging", lambda: None)
    return database


def _parent(database: FakeDatabase) -> TenantId:
    [user] = database.factory.state.users.values()
    return user.tenant_id


def _personal_data(dataset: SyntheticDataset, trade: Trade) -> list[str]:
    data = dataset.professional(trade)
    pro = data.professional
    values = [pro.name, pro.tax_id, pro.address, EMAIL]
    for customer in data.customers:
        values += [customer.name, customer.tax_id, customer.address]
    return values


@pytest.mark.req("RF-CF-04")
def test_la_orden_carga_y_solo_muestra_ids_y_conteos(
    fake_db, dataset: SyntheticDataset, capsys, captured_logs
):
    code = seed_demo.main(["--account", EMAIL, "--trade", "electricista"])

    assert code == seed_demo.EXIT_OK
    data = dataset.professional(Trade.ELECTRICIAN)
    parent = _parent(fake_db)
    demo_id = demo_tenant_id(parent)
    out = capsys.readouterr().out
    assert out == (
        f"Espacio de demostración creado. demo_tenant_id={demo_id} profesional=1 "
        f"clientes={len(data.customers)} catalogo={len(data.catalog)} "
        f"presupuestos={len(data.quotes)}\n"
    )
    [event] = [json.loads(line) for line in captured_logs.getvalue().splitlines()]
    assert event["event"] == "demo_space_loaded"
    assert (event["tenant_id"], event["demo_tenant_id"]) == (str(parent), str(demo_id))
    assert event["quotes"] == len(data.quotes)
    logged = out + captured_logs.getvalue()
    assert not [value for value in _personal_data(dataset, Trade.ELECTRICIAN) if value in logged]
    assert fake_db.disposed == 1


@pytest.mark.req("RF-CF-04")
def test_la_orden_admite_el_id_de_la_cuenta(fake_db, capsys):
    parent = _parent(fake_db)

    code = seed_demo.main(["--account-id", str(parent), "--trade", "albanil"])

    assert code == seed_demo.EXIT_OK
    assert f"demo_tenant_id={demo_tenant_id(parent)}" in capsys.readouterr().out
    assert demo_tenant_id(parent) in fake_db.factory.state.tenants


@pytest.mark.req("RF-CF-04")
def test_la_orden_falla_con_mensaje_claro_y_sin_datos_personales(fake_db, capsys):
    assert seed_demo.main(["--account", EMAIL, "--trade", "albanil", "--seed", "7"]) == 0
    capsys.readouterr()
    before = fake_db.factory.state.copy()

    assert seed_demo.main(["--account", EMAIL, "--trade", "electricista"]) == seed_demo.EXIT_ERROR
    err = capsys.readouterr().err
    assert "ya tiene un espacio de demostración" in err

    code = seed_demo.main(["--account", "nadie@example.com", "--trade", "albanil"])
    assert code == seed_demo.EXIT_ERROR
    err = capsys.readouterr().err
    assert "No hay ninguna cuenta con ese email" in err
    assert "nadie@example.com" not in err

    missing = uuid4()
    code = seed_demo.main(["--account-id", str(missing), "--trade", "albanil"])
    assert code == seed_demo.EXIT_ERROR
    assert "La cuenta no existe" in capsys.readouterr().err
    assert fake_db.factory.state == before


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize(
    "argv",
    [
        ["--account", EMAIL, "--trade", "fontanero"],
        ["--account", EMAIL, "--account-id", str(uuid4()), "--trade", "albanil"],
        ["--trade", "albanil"],
        ["--account-id", "no-es-un-uuid", "--trade", "albanil"],
    ],
    ids=["oficio-desconocido", "email-e-id-a-la-vez", "sin-cuenta", "id-no-valido"],
)
def test_la_orden_rechaza_argumentos_no_validos(fake_db, capsys, argv):
    with pytest.raises(SystemExit) as exit_info:
        seed_demo.main(argv)
    assert exit_info.value.code == 2
    assert "seed_demo" in capsys.readouterr().err
    assert len(fake_db.factory.state.tenants) == 1


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
@pytest.mark.parametrize(
    ("role", "reason"),
    [
        ({"superuser": True}, "es superusuario"),
        ({"bypass_rls": True}, "tiene BYPASSRLS"),
        ({"table_owner": True}, "propietario de las tablas"),
    ],
)
def test_la_orden_se_niega_con_un_rol_que_se_salta_rls(fake_db, capsys, role, reason):
    """S3-07: antes de cargar nada; RLS no filtraría lo que escribe."""
    fake_db.role = seed_demo.ConnectedRole(
        **{"superuser": False, "bypass_rls": False, "table_owner": False, **role}
    )
    before = fake_db.factory.state.copy()

    code = seed_demo.main(["--account", EMAIL, "--trade", "albanil"])

    assert code == seed_demo.EXIT_ERROR
    err = capsys.readouterr().err
    assert reason in err
    assert "kapataz_app" in err
    assert fake_db.factory.state == before
    assert fake_db.disposed == 1


def _integrity_error() -> IntegrityError:
    orig = Exception(f"duplicate key value\nDETAIL:  Key (tax_id)=({SECRET}) already exists.")
    return IntegrityError("INSERT INTO customers ...", {"tax_id": SECRET}, orig)


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize(
    "error",
    [
        _integrity_error(),
        OperationalError("SELECT 1", {}, Exception(f"connection lost {SECRET}")),
        ConnectionRefusedError(f"[Errno 111] Connect call failed ('{SECRET}', 5432)"),
        TimeoutError(),
    ],
    ids=["sqlalchemy", "operacional", "conexion-rechazada", "tiempo-agotado"],
)
def test_un_error_de_base_de_datos_sale_con_un_mensaje_fijo(fake_db, capsys, captured_logs, error):
    """S3-08: sin traza ni DETAIL, que podrían llevar datos; el log solo lleva el tipo."""
    fake_db.role_error = error

    code = seed_demo.main(["--account", EMAIL, "--trade", "albanil"])

    assert code == seed_demo.EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.err == seed_demo.DATABASE_FAILED
    assert captured.out == ""
    [event] = [json.loads(line) for line in captured_logs.getvalue().splitlines()]
    assert (event["event"], event["error_type"]) == ("demo_space_failed", type(error).__name__)
    assert SECRET not in captured_logs.getvalue()
    assert fake_db.disposed == 1


@pytest.mark.req("RF-CF-04")
def test_un_error_de_base_de_datos_a_mitad_de_la_carga_tambien(fake_db, capsys, monkeypatch):
    async def fails(*_args, **_kwargs):
        raise _integrity_error()

    monkeypatch.setattr(seed_demo, "seed_demo", fails)

    assert seed_demo.main(["--account", EMAIL, "--trade", "albanil"]) == seed_demo.EXIT_ERROR
    assert capsys.readouterr().err == seed_demo.DATABASE_FAILED


@pytest.mark.req("RF-CF-04")
def test_sin_postgresql_la_conexion_rechazada_sale_con_el_mensaje_fijo(monkeypatch, capsys):
    """El motor de verdad contra un puerto cerrado: asyncpg lanza OSError sin envolver."""
    monkeypatch.setattr(
        seed_demo,
        "Settings",
        lambda: make_settings(database_url="postgresql://kapataz_app:x@127.0.0.1:9/kapataz"),
    )
    monkeypatch.setattr(seed_demo, "configure_logging", lambda: None)

    code = seed_demo.main(["--account-id", str(uuid4()), "--trade", "albanil"])

    assert code == seed_demo.EXIT_ERROR
    assert capsys.readouterr().err == seed_demo.DATABASE_FAILED
