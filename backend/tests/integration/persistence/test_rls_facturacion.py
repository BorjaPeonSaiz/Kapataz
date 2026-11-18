"""RLS y claves foráneas compuestas en las tablas de facturación (RN-10, RNF-13, ADR-024)."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from kapataz.application.ports.repositories import TenantMismatchError, TenantNotSetError
from tests.billing_support import add_customer, create_account, draft_invoice
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import issue_new, run_sql

BILLING_TABLES = (
    "professional",
    "customers",
    "catalog_items",
    "quotes",
    "quote_versions",
    "quote_lines",
    "invoices",
    "invoice_lines",
    "invoice_corrections",
    "series_counters",
    "billing_chain_heads",
    "billing_records",
    "payments",
)


@pytest.mark.req("RNF-13")
def test_cada_tabla_de_facturacion_tiene_rls_y_su_politica(database):
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT c.relname, c.relrowsecurity, count(p.policyname) "
        "FROM pg_class c LEFT JOIN pg_policies p ON p.tablename = c.relname "
        "WHERE c.relname = ANY(:tables) GROUP BY c.relname, c.relrowsecurity",
        {"tables": list(BILLING_TABLES)},
    )
    assert {row[0]: (row[1], row[2]) for row in rows} == dict.fromkeys(BILLING_TABLES, (True, 1))


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
@pytest.mark.parametrize("table", BILLING_TABLES)
def test_a01_sin_cuenta_fijada_no_hay_filas(app_factory, database, table):
    issue_new(app_factory)  # Garantiza filas en todas las tablas de la emisión.

    assert run_sql(database, APP_ROLE, f"SELECT count(*) FROM {table}") == [(0,)]


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_una_cuenta_no_ve_la_facturacion_de_otra(app_factory, database):
    mine, [my_invoice] = issue_new(app_factory)
    other, [other_invoice] = issue_new(app_factory)

    async def read_other_from_mine():
        async with app_factory() as uow:
            await uow.set_tenant(mine)
            return (
                await uow.invoices.get(other_invoice.invoice.id),
                await uow.customers.get(other_invoice.invoice.customer_id),
                await uow.billing_chain.list_chain(),
            )

    invoice, customer, chain = asyncio.run(read_other_from_mine())
    assert invoice is None
    assert customer is None
    assert chain == (my_invoice.record,)
    for table in ("invoices", "invoice_lines", "billing_records", "series_counters"):
        rows = run_sql(
            database, APP_ROLE, f"SELECT DISTINCT tenant_id FROM {table}", tenant_id=mine
        )
        assert rows == [(mine,)], table
    del other


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_no_se_escribe_en_otra_cuenta(app_factory, database):
    mine = asyncio.run(create_account(app_factory))
    other = asyncio.run(create_account(app_factory))
    other_customer = asyncio.run(add_customer(app_factory, other))

    # El código lo rechaza antes de llegar a la base de datos…
    async def add_foreign_draft():
        async with app_factory() as uow:
            await uow.set_tenant(mine)
            await uow.invoices.add_draft(draft_invoice(other, other_customer))

    with pytest.raises(TenantMismatchError):
        asyncio.run(add_foreign_draft())

    # …y RLS también, por SQL directo (WITH CHECK).
    with pytest.raises(DBAPIError, match="row-level security"):
        run_sql(
            database,
            APP_ROLE,
            "INSERT INTO customers (id, tenant_id, name, created_at) "
            "VALUES (:id, :other, 'Intruso', now())",
            {"id": uuid4(), "other": other},
            tenant_id=mine,
        )


@pytest.mark.req("RNF-13")
def test_las_claves_compuestas_no_enlazan_filas_de_cuentas_distintas(app_factory, database):
    mine = asyncio.run(create_account(app_factory))
    other = asyncio.run(create_account(app_factory))
    other_customer = asyncio.run(add_customer(app_factory, other))

    # Ni siquiera el propietario, que no pasa por RLS, cuela una factura de una
    # cuenta con el cliente de otra.
    with pytest.raises(DBAPIError, match="fk_invoices_customer"):
        run_sql(
            database,
            OWNER_ROLE,
            "INSERT INTO invoices (id, tenant_id, customer_id, status, invoice_type, series, "
            "regime_key, operation_class, tax_rate, base_total, tax_total, total_amount, "
            "withholding_amount, guarantee_amount, amount_due, created_at) "
            "VALUES (:id, :mine, :customer, 'draft', 'F1', 'F', '01', 'S1', 21, "
            "0, 0, 0, 0, 0, 0, now())",
            {"id": uuid4(), "mine": mine, "customer": other_customer},
        )


@pytest.mark.req("RNF-13")
def test_un_repositorio_de_negocio_sin_cuenta_fijada_falla(app_factory):
    async def without_tenant():
        async with app_factory() as uow:
            await uow.invoices.get(uuid4())

    with pytest.raises(TenantNotSetError):
        asyncio.run(without_tenant())
