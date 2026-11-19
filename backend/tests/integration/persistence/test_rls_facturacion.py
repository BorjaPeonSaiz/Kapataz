"""RLS y claves foráneas compuestas en las tablas de negocio (RN-10, RNF-13, ADR-024).

Las tablas de negocio salen del catálogo de PostgreSQL, no de una lista escrita
a mano: todas las del esquema ``public`` menos la lista cerrada de tablas
globales (arquitectura §5.4, ADR-024) y la de Alembic. Una tabla nueva entra
sola en estas pruebas, y si no tiene RLS con su política, el CI falla.
"""

import asyncio
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from kapataz.application.ports.repositories import TenantMismatchError, TenantNotSetError
from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.ids import PaymentId, QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.payment import Payment, PaymentMethod
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.quote import PriceSource, Quote, QuoteLine, QuoteStatus, QuoteVersion
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from kapataz.infrastructure.persistence.tables import GLOBAL_TABLES_WITHOUT_RLS
from tests.billing_support import (
    SEED_AT,
    add_corrective_draft,
    add_customer,
    add_draft,
    create_account,
    draft_invoice,
)
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import issue_new, issue_use_case, run_sql

# Lista cerrada de tablas globales sin RLS, tal como la fijan la arquitectura
# (§5.4) y ADR-024. Se escribe aquí y no se importa: si alguien amplía la
# constante del código, esta prueba lo detecta.
DOCUMENTED_GLOBAL_TABLES = frozenset(
    {
        "users",
        "sessions",
        "email_verifications",
        "subscriptions",
        "payment_events",
        "platform_settings",
        "platform_admins",
        "platform_audit_events",
    }
)
# Tabla de Alembic: no es de negocio y la app no tiene permisos sobre ella.
INFRASTRUCTURE_TABLES = frozenset({"alembic_version"})

# Tablas de negocio que existen hoy: el recorrido del catálogo no puede salir vacío.
KNOWN_BUSINESS_TABLES = frozenset(
    {
        "tenants",
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
    }
)

# Enlaces entre cuentas que son a propósito: la cuenta de cortesía o de
# demostración apunta a la cuenta de la que depende (RN-13). Es la tabla de
# cuentas, no un dato de negocio de una cuenta que pueda verse desde otra.
ACCOUNT_LINKS = frozenset({"fk_tenants_parent_tenant_id_tenants"})

_CURRENT_TENANT = "(NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid"


def _tenant_column(table: str) -> str:
    """Columna con la cuenta: ``id`` en ``tenants``, ``tenant_id`` en las demás."""
    return "id" if table == "tenants" else "tenant_id"


def _business_tables(database) -> list[str]:
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') ORDER BY c.relname",
    )
    excluded = DOCUMENTED_GLOBAL_TABLES | INFRASTRUCTURE_TABLES
    return [name for (name,) in rows if name not in excluded]


# ------------------------------------------------------- datos en cada tabla


@dataclass(frozen=True)
class SeededAccount:
    """Una cuenta con al menos una fila en cada tabla de negocio."""

    tenant_id: TenantId
    customer_id: UUID
    quote_id: UUID
    quote_version_id: UUID
    quote_line_id: UUID
    issued_invoice_id: UUID
    draft_invoice_id: UUID
    corrective_invoice_id: UUID
    payment_id: UUID


def _seed_every_table(factory) -> SeededAccount:
    tenant_id = asyncio.run(create_account(factory))  # tenants y professional
    customer_id = asyncio.run(add_customer(factory, tenant_id))
    quote_line = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Alicatado",
        quantity=Quantity(Decimal(12)),
        unit_price=Money.of("24.50"),
        price_source=PriceSource.manual(),
    )
    version = QuoteVersion(
        id=QuoteVersionId(uuid4()),
        version=1,
        lines=(quote_line,),
        recipient_type=RecipientType.PRIVATE,
        dwelling_over_two_years=True,
        valid_until=date(2026, 12, 31),
        created_at=SEED_AT,
    )
    quote = Quote(
        id=QuoteId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        number=DocumentNumber(Series.quotes(), 2026, 1),
        status=QuoteStatus.DRAFT,
        versions=(version,),
        created_at=SEED_AT,
    )
    item = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept="Punto de luz",
        unit="ud",
        reference_price=Money.of("45.90"),
        origin=CatalogItemOrigin.MANUAL,
        is_material=False,
        created_at=SEED_AT,
    )
    issued_draft = asyncio.run(add_draft(factory, tenant_id, customer_id))
    # invoices, invoice_lines, series_counters, billing_chain_heads y billing_records.
    issued = asyncio.run(issue_use_case(factory).execute(tenant_id, issued_draft)).invoice
    draft_id = asyncio.run(add_draft(factory, tenant_id, customer_id))
    corrective_id = asyncio.run(add_corrective_draft(factory, tenant_id, customer_id, issued))
    payment = Payment(
        id=PaymentId(uuid4()),
        tenant_id=tenant_id,
        invoice_id=issued.id,
        amount=Money.of("100.00"),
        paid_at=date(2026, 11, 20),
        method=PaymentMethod.TRANSFER,
        created_at=SEED_AT,
    )

    async def add_rest():
        async with factory() as uow:
            await uow.set_tenant(tenant_id)
            await uow.quotes.add(quote)
            await uow.catalog.add(item)
            await uow.payments.add(payment)
            await uow.commit()

    asyncio.run(add_rest())
    return SeededAccount(
        tenant_id=tenant_id,
        customer_id=customer_id,
        quote_id=quote.id,
        quote_version_id=version.id,
        quote_line_id=quote_line.id,
        issued_invoice_id=issued.id,
        draft_invoice_id=draft_id,
        corrective_invoice_id=corrective_id,
        payment_id=payment.id,
    )


def _as_app(database, tenant_setting, statements):
    """Cada sentencia en su propio punto de guardado, con el rol de la app.

    ``tenant_setting`` es el valor de ``app.tenant_id``, o ``None`` para no
    fijarlo. Devuelve, por sentencia, ``("filas", n)`` con las filas devueltas o
    afectadas, o ``("error", mensaje)``. Al final lo deshace todo.
    """

    async def run() -> list[tuple[str, object]]:
        engine = database.engine(APP_ROLE)
        results: list[tuple[str, object]] = []
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                if tenant_setting is not None:
                    await conn.execute(
                        text("SELECT set_config('app.tenant_id', :t, true)"),
                        {"t": str(tenant_setting)},
                    )
                for statement, params in statements:
                    try:
                        async with conn.begin_nested():
                            result = await conn.execute(text(statement), dict(params))
                            count = result.scalar() if result.returns_rows else result.rowcount
                            results.append(("filas", count))
                    except DBAPIError as error:
                        results.append(("error", str(error.orig)))
                await transaction.rollback()
        finally:
            await engine.dispose()
        return results

    return asyncio.run(run())


def _privileges(database, tables) -> dict[str, tuple[bool, bool]]:
    """(UPDATE, DELETE) del rol de la app en cada tabla."""
    rows = run_sql(
        database,
        APP_ROLE,
        "SELECT t, has_table_privilege(current_user, t, 'UPDATE'), "
        "has_table_privilege(current_user, t, 'DELETE') FROM unnest(CAST(:tables AS text[])) t",
        {"tables": list(tables)},
    )
    return {table: (update, delete) for table, update, delete in rows}


def _row_as_json(database, table, tenant_id) -> str:
    """Una fila de la cuenta en JSON, apta para volver a insertarla tal cual."""
    column = _tenant_column(table)
    # El primer registro no tiene anterior: su copia no tropieza con el trigger
    # que comprueba el enlace, y lo que la rechaza es RLS. La cabeza se copia
    # vacía, que es como el trigger deja nacerla.
    extra = " AND previous_record_id IS NULL" if table == "billing_records" else ""
    patch = " || '{\"last_record_id\": null}'" if table == "billing_chain_heads" else ""
    rows = run_sql(
        database,
        OWNER_ROLE,
        f"SELECT (to_jsonb(t){patch})::text FROM {table} t WHERE {column} = :t{extra} LIMIT 1",
        {"t": tenant_id},
    )
    # Una tabla nueva sin filas dejaría la prueba vacía: hay que darle datos.
    assert rows, f"La cuenta no tiene filas en {table}: añádela a _seed_every_table."
    return rows[0][0]


def _copy_row(table: str, where: str, changes: str) -> str:
    """INSERT que copia una fila visible de ``table`` con los cambios de ``changes``."""
    return (
        f"INSERT INTO {table} SELECT (jsonb_populate_record(NULL::{table}, "
        f"to_jsonb(t) || jsonb_build_object({changes}))).* FROM {table} t WHERE {where}"
    )


def _insert_json(table: str) -> str:
    return (
        f"INSERT INTO {table} SELECT (jsonb_populate_record(NULL::{table}, CAST(:row AS jsonb))).*"
    )


# ----------------------------------------------------------- catálogo


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_toda_tabla_de_negocio_tiene_rls_y_la_politica_de_la_cuenta(database):
    assert GLOBAL_TABLES_WITHOUT_RLS == DOCUMENTED_GLOBAL_TABLES
    tables = _business_tables(database)
    assert set(tables) >= KNOWN_BUSINESS_TABLES

    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT c.relname, c.relrowsecurity, "
        "(SELECT a.attnotnull FROM pg_attribute a WHERE a.attrelid = c.oid "
        " AND a.attname = CASE WHEN c.relname = 'tenants' THEN 'id' ELSE 'tenant_id' END "
        " AND NOT a.attisdropped), "
        "COALESCE((SELECT array_agg(ARRAY[p.permissive, p.cmd, array_to_string(p.roles, ','), "
        " p.qual, COALESCE(p.with_check, '')] ORDER BY p.policyname) "
        " FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname), "
        " '{}') "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = ANY(CAST(:tables AS text[]))",
        {"tables": tables},
    )
    found = {name: (rls, not_null, policies) for name, rls, not_null, policies in rows}
    problems = {}
    for table in tables:
        rls, not_null, policies = found[table]
        expected = f"({_tenant_column(table)} = {_CURRENT_TENANT})"
        # Una sola política, para todas las órdenes y todos los roles, que
        # filtra y comprueba por la cuenta fijada en la transacción.
        if (
            not rls
            or not not_null
            or policies != [["PERMISSIVE", "ALL", "public", expected, expected]]
        ):
            problems[table] = (rls, not_null, policies)
    assert problems == {}, f"Tablas de negocio sin RLS o con otra política: {problems}"


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_ninguna_vista_salta_rls(database):
    # Una vista se evalúa con los permisos de su dueño, que no pasa por RLS, y
    # una vista materializada no admite RLS. Si la app pudiera leer alguna, se
    # saltaría el aislamiento salvo que la vista lleve security_invoker.
    rows = run_sql(
        database,
        APP_ROLE,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm') "
        "AND has_table_privilege(current_user, c.oid, 'SELECT') "
        "AND NOT (c.relkind = 'v' AND 'security_invoker=true' = ANY(COALESCE(c.reloptions, '{}')))",
    )
    assert rows == []


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_toda_clave_foranea_entre_tablas_de_negocio_lleva_la_cuenta(database):
    tables = _business_tables(database)
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT con.conname, child.relname, parent.relname, "
        "(SELECT attname FROM pg_attribute WHERE attrelid = con.conrelid "
        " AND attnum = con.conkey[1]), "
        "(SELECT attname FROM pg_attribute WHERE attrelid = con.confrelid "
        " AND attnum = con.confkey[1]), cardinality(con.conkey) "
        "FROM pg_constraint con "
        "JOIN pg_class child ON child.oid = con.conrelid "
        "JOIN pg_class parent ON parent.oid = con.confrelid "
        "WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace "
        "AND child.relname = ANY(CAST(:tables AS text[]))",
        {"tables": tables},
    )
    composite = 0
    problems = []
    for name, child, parent, child_first, parent_first, size in rows:
        if parent == "tenants" and size == 1 and child_first == _tenant_column(child):
            continue  # La propia cuenta.
        if name in ACCOUNT_LINKS:
            continue
        composite += 1
        # Entre tablas de negocio: (tenant_id, …) contra (tenant_id, …), y nunca
        # hacia una tabla global, que no tiene RLS.
        if (
            parent not in tables
            or size < 2
            or child_first != "tenant_id"
            or parent_first != "tenant_id"
        ):
            problems.append((name, child, parent, child_first, parent_first, size))
    assert problems == []
    assert composite >= 14  # Las catorce de la migración 0003.


# --------------------------------------------------------- sin cuenta fijada


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
@pytest.mark.parametrize("setting", [None, ""], ids=["sin-fijar", "vacia"])
def test_a01_sin_cuenta_fijada_ninguna_tabla_de_negocio_da_ni_toca_filas(
    app_factory, database, setting
):
    seeded = _seed_every_table(app_factory)
    tables = _business_tables(database)
    privileges = _privileges(database, tables)

    for table in tables:
        column = _tenant_column(table)
        # La cuenta tiene filas en la tabla (si no, falla aquí): la prueba no es vacía.
        own_row = _row_as_json(database, table, seeded.tenant_id)
        can_update, can_delete = privileges[table]
        statements = [(f"SELECT count(*) FROM {table}", {})]
        if can_update:
            statements.append((f"UPDATE {table} SET {column} = {column}", {}))
        if can_delete:
            statements.append((f"DELETE FROM {table}", {}))
        statements.append((_insert_json(table), {"row": own_row}))

        *reads_and_writes, insert = _as_app(database, setting, statements)

        assert reads_and_writes == [("filas", 0)] * len(reads_and_writes), table
        assert insert[0] == "error"
        assert "row-level security" in insert[1], (table, insert)


# ------------------------------------------------------- entre dos cuentas


@pytest.mark.req("RN-10")
@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_a01_una_cuenta_no_lee_ni_escribe_filas_de_otra_en_ninguna_tabla(app_factory, database):
    mine = _seed_every_table(app_factory)
    other = _seed_every_table(app_factory)
    tables = _business_tables(database)
    privileges = _privileges(database, tables)

    for table in tables:
        column = _tenant_column(table)
        ids = {"mine": mine.tenant_id, "other": other.tenant_id}
        can_update, can_delete = privileges[table]
        statements = [
            (f"SELECT count(*) FROM {table} WHERE {column} = :mine", ids),
            (f"SELECT count(*) FROM {table} WHERE {column} = :other", ids),
            (f"SELECT count(*) FROM {table} WHERE {column} <> :mine", ids),
        ]
        expected = [("filas", "alguna"), ("filas", 0), ("filas", 0)]
        if can_update:
            statements.append(
                (f"UPDATE {table} SET {column} = {column} WHERE {column} = :other", ids)
            )
            expected.append(("filas", 0))
        if can_delete:
            statements.append((f"DELETE FROM {table} WHERE {column} = :other", ids))
            expected.append(("filas", 0))
        # Escribir en la otra cuenta: su propia fila, copiada tal cual…
        statements.append(
            (_insert_json(table), {"row": _row_as_json(database, table, other.tenant_id)})
        )
        expected.append(("error", "row-level security"))
        # …o pasar una fila propia a la otra cuenta.
        if can_update:
            statements.append((f"UPDATE {table} SET {column} = :other WHERE {column} = :mine", ids))
            expected.append(("error", "row-level security|RN-F-0"))

        results = _as_app(database, mine.tenant_id, statements)

        for (kind, value), (expected_kind, expected_value) in zip(results, expected, strict=True):
            assert kind == expected_kind, (table, kind, value)
            if expected_value == "alguna":
                assert value > 0, table
            elif kind == "error":
                assert any(part in value for part in expected_value.split("|")), (table, value)
            else:
                assert value == expected_value, (table, value)


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


# ------------------------------------------------ claves foráneas compuestas


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
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
@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_con_la_cuenta_fijada_ninguna_clave_compuesta_enlaza_con_otra_cuenta(app_factory, database):
    # La cuenta fijada es la propia y la fila sigue siendo de ella, así que RLS
    # la deja pasar. Lo que la para es la clave foránea (tenant_id, …): el id
    # existe, pero en otra cuenta.
    a = _seed_every_table(app_factory)
    b = _seed_every_table(app_factory)
    ids = {
        "a_draft": a.draft_invoice_id,
        "a_quote": a.quote_id,
        "a_version": a.quote_version_id,
        "a_quote_line": a.quote_line_id,
        "a_payment": a.payment_id,
        "a_corrective": a.corrective_invoice_id,
        "b_customer": b.customer_id,
        "b_quote": b.quote_id,
        "b_version": b.quote_version_id,
        "b_quote_line": b.quote_line_id,
        "b_issued": b.issued_invoice_id,
        "b_draft": b.draft_invoice_id,
    }
    first_line = "invoice_id = :a_draft AND position = 1"
    cases = {
        "fk_invoices_customer": "UPDATE invoices SET customer_id = :b_customer WHERE id = :a_draft",
        "fk_invoices_quote_version": (
            "UPDATE invoices SET quote_version_id = :b_version, recipient_type = NULL, "
            "dwelling_over_two_years = NULL WHERE id = :a_draft"
        ),
        "fk_invoice_lines_invoice": (
            f"UPDATE invoice_lines SET invoice_id = :b_draft WHERE {first_line}"
        ),
        "fk_invoice_lines_quote_line": (
            "UPDATE invoice_lines SET origin = 'quote', quote_line_id = :b_quote_line "
            f"WHERE {first_line}"
        ),
        "fk_invoice_lines_prior_invoice": (
            "UPDATE invoice_lines SET origin = 'prior_invoice', prior_invoice_id = :b_issued "
            f"WHERE {first_line}"
        ),
        "fk_quotes_customer": "UPDATE quotes SET customer_id = :b_customer WHERE id = :a_quote",
        "fk_quote_versions_quote": (
            "UPDATE quote_versions SET quote_id = :b_quote WHERE id = :a_version"
        ),
        "fk_quote_lines_quote_version": (
            "UPDATE quote_lines SET quote_version_id = :b_version WHERE id = :a_quote_line"
        ),
        # Sin UPDATE en estas dos: se copia una fila propia cambiando el enlace.
        "fk_payments_invoice": _copy_row(
            "payments",
            "id = :a_payment",
            "'id', gen_random_uuid(), 'invoice_id', CAST(:b_issued AS uuid)",
        ),
        "fk_invoice_corrections_rectified": _copy_row(
            "invoice_corrections",
            "corrective_invoice_id = :a_corrective",
            "'rectified_invoice_id', CAST(:b_issued AS uuid), 'position', 2",
        ),
    }

    results = _as_app(database, a.tenant_id, [(sql, ids) for sql in cases.values()])

    for constraint, (kind, message) in zip(cases, results, strict=True):
        assert kind == "error", (constraint, message)
        assert f'foreign key constraint "{constraint}"' in message, (constraint, message)


@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A01")
def test_un_repositorio_de_negocio_sin_cuenta_fijada_falla(app_factory):
    async def without_tenant():
        async with app_factory() as uow:
            await uow.invoices.get(uuid4())

    with pytest.raises(TenantNotSetError):
        asyncio.run(without_tenant())
