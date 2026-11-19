"""Los triggers de facturación no se dejan engañar por tablas temporales (S2-01).

Sin ``search_path`` fijo, una función plpgsql resuelve los nombres sin esquema
buscando primero en ``pg_temp``. Con ``TEMPORARY`` sobre la base de datos, la
app podía crear una tabla temporal ``invoices`` con la factura emitida como
borrador y el trigger dejaba cambiar sus líneas. Dos defensas, y una prueba
para cada una:

- ni ``PUBLIC`` ni ``kapataz_app`` crean tablas temporales;
- cada función de trigger fija ``search_path = pg_catalog, public, pg_temp`` y
  nombra sus tablas con el esquema. El propietario sí puede crear tablas
  temporales, y con él se repite el ataque contra cada trigger que consulta
  tablas: los triggers actúan también para el propietario.
"""

import asyncio
from datetime import date

import pytest

from tests.billing_support import add_corrective_draft, add_customer, add_draft, create_account
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import ISSUE_AT, issue_new, issue_use_case, run_sql
from tests.integration.persistence.sql_support import attempt

SEARCH_PATH = "search_path=pg_catalog, public, pg_temp"

# Una tabla temporal que se hace pasar por invoices, con la factura en borrador.
_SHADOW_INVOICES = [
    ("CREATE TEMP TABLE invoices (id uuid, status text)", {}),
    ("INSERT INTO pg_temp.invoices VALUES (:id, 'draft')", {}),
]


def _shadow_records(extra: str = "") -> list[tuple[str, dict[str, object]]]:
    """Copia temporal de billing_records con la fila :id, retocada con ``extra``."""
    statements: list[tuple[str, dict[str, object]]] = [
        ("CREATE TEMP TABLE billing_records (LIKE public.billing_records)", {}),
        (
            (
                "INSERT INTO pg_temp.billing_records "
                "SELECT * FROM public.billing_records WHERE id = :id"
            ),
            {},
        ),
    ]
    if extra:
        statements.append((f"UPDATE pg_temp.billing_records SET {extra}", {}))
    return statements


def _with(params, statements):
    return [(sql, {**params, **own}) for sql, own in statements]


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RN-F-07")
@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A08")
def test_toda_funcion_del_esquema_fija_el_search_path(database):
    # Todas las funciones y procedimientos de public, no solo los de trigger:
    # una función auxiliar a la que llame un trigger tiene el mismo riesgo. Las
    # de una extensión (pgvector, por ejemplo) no son nuestras y se excluyen.
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT p.oid::regprocedure::text, p.prorettype = 'trigger'::regtype, p.proconfig "
        "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
        "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass "
        "AND d.objid = p.oid AND d.deptype = 'e') ORDER BY 1",
    )
    # La migración 0003 crea trece de trigger y una auxiliar: el catálogo no sale vacío.
    assert sum(1 for _, is_trigger, _ in rows if is_trigger) >= 13
    assert "invoice_series_number(text,integer,integer)" in {name for name, _, _ in rows}
    without = {name: config for name, _, config in rows if SEARCH_PATH not in (config or [])}
    assert without == {}, f"Funciones sin search_path fijo: {without}"


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RNF-13")
@pytest.mark.owasp("A08")
def test_ni_public_ni_la_app_crean_tablas_temporales(app_factory, database):
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT has_database_privilege('public', current_database(), 'TEMPORARY'), "
        "has_database_privilege(:app, current_database(), 'TEMPORARY')",
        {"app": APP_ROLE},
    )
    assert rows == [(False, False)]

    # El ataque reproducido en la revisión se para en el primer paso.
    tenant_id, [issued] = issue_new(app_factory)
    rejection = attempt(
        database,
        APP_ROLE,
        [
            *_with({"id": issued.invoice.id}, _SHADOW_INVOICES),
            (
                "UPDATE public.invoice_lines SET description = 'alterada' WHERE invoice_id = :id",
                {"id": issued.invoice.id},
            ),
        ],
        tenant_id=tenant_id,
    )
    assert rejection is not None
    assert rejection.sqlstate == "42501", rejection  # insufficient_privilege
    assert "temporary" in rejection.message.lower()


@pytest.mark.req("RN-F-02")
@pytest.mark.owasp("A08")
def test_una_tabla_temporal_no_desbloquea_las_lineas_de_una_emitida(app_factory, database):
    tenant_id, [issued] = issue_new(app_factory)
    params = {"id": issued.invoice.id}

    rejection = attempt(
        database,
        OWNER_ROLE,
        _with(
            params,
            [
                *_SHADOW_INVOICES,
                (
                    (
                        "UPDATE public.invoice_lines SET description = 'alterada' "
                        "WHERE invoice_id = :id"
                    ),
                    {},
                ),
            ],
        ),
        tenant_id=tenant_id,
    )

    assert rejection is not None
    assert (rejection.sqlstate, "RN-F-02" in rejection.message) == ("KZF02", True)


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RN-F-03")
@pytest.mark.owasp("A08")
def test_una_tabla_temporal_no_desbloquea_lo_rectificado_por_una_emitida(app_factory, database):
    tenant_id, [original] = issue_new(app_factory)
    corrective_id = asyncio.run(
        add_corrective_draft(app_factory, tenant_id, original.invoice.customer_id, original.invoice)
    )
    asyncio.run(issue_use_case(app_factory).execute(tenant_id, corrective_id))

    rejection = attempt(
        database,
        OWNER_ROLE,
        _with(
            {"id": corrective_id},
            [
                *_SHADOW_INVOICES,
                (
                    (
                        "UPDATE public.invoice_corrections SET position = 2 "
                        "WHERE corrective_invoice_id = :id"
                    ),
                    {},
                ),
            ],
        ),
    )

    assert rejection is not None
    assert (rejection.sqlstate, "RN-F-02" in rejection.message) == ("KZF02", True)


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
def test_una_tabla_temporal_no_falsea_el_enlace_de_un_registro(app_factory, database):
    # La copia temporal del último registro lleva otra huella; el registro nuevo
    # enlaza con esa huella falsa. El trigger tiene que leer el de verdad.
    _, [issued] = issue_new(app_factory)
    params = {"id": issued.record.id}
    linked_to_fake_hash = (
        "INSERT INTO public.billing_records SELECT (jsonb_populate_record("
        "NULL::public.billing_records, to_jsonb(r) || jsonb_build_object("
        "'id', gen_random_uuid(), 'previous_record_id', r.id, 'is_first', false, "
        "'prev_issuer_tax_id', r.issuer_tax_id, 'prev_series_number', r.series_number, "
        "'prev_issue_date', r.issue_date, 'prev_hash', repeat('B', 64)))).* "
        "FROM public.billing_records r WHERE r.id = :id"
    )

    rejection = attempt(
        database,
        OWNER_ROLE,
        _with(params, [*_shadow_records("hash = repeat('B', 64)"), (linked_to_fake_hash, {})]),
    )

    assert rejection is not None
    assert rejection.sqlstate == "KZF07", rejection
    assert "el enlace no copia" in rejection.message


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
def test_una_tabla_temporal_no_hace_retroceder_la_cabeza(app_factory, database):
    # En la copia temporal, el primer registro «enlaza» con el segundo: la
    # cabeza volvería al primero como si fuera el siguiente.
    tenant_id, [first, second] = issue_new(app_factory, 2)
    params = {"id": first.record.id, "second": second.record.id, "t": tenant_id}

    rejection = attempt(
        database,
        OWNER_ROLE,
        _with(
            params,
            [
                *_shadow_records("previous_record_id = CAST(:second AS uuid)"),
                (
                    (
                        "UPDATE public.billing_chain_heads SET last_record_id = :id "
                        "WHERE tenant_id = :t"
                    ),
                    {},
                ),
            ],
        ),
    )

    assert rejection is not None
    assert rejection.sqlstate == "KZF07", rejection
    assert "solo avanza al registro siguiente" in rejection.message


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
def test_tablas_temporales_no_sustituyen_al_contador_ni_al_registro(app_factory, database):
    # Una emisión por SQL sin contador ni registro, con copias temporales que sí
    # los tienen. Los triggers diferidos tienen que mirar las tablas de verdad.
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, customer_id))
    params = {
        "id": draft_id,
        "t": tenant_id,
        "d": date(2026, 11, 18),
        "at": ISSUE_AT,
    }

    rejection = attempt(
        database,
        OWNER_ROLE,
        _with(
            params,
            [
                ("CREATE TEMP TABLE series_counters (LIKE public.series_counters)", {}),
                ("INSERT INTO pg_temp.series_counters VALUES (:t, 'F', 2026, 1, :d)", {}),
                (
                    (
                        "CREATE TEMP TABLE billing_records (id uuid, tenant_id uuid, "
                        "invoice_id uuid, previous_record_id uuid, record_type text, "
                        "issuer_tax_id text, issue_date date)"
                    ),
                    {},
                ),
                (
                    (
                        "INSERT INTO pg_temp.billing_records (id, tenant_id, invoice_id, "
                        "record_type, issuer_tax_id, issue_date) "
                        "VALUES (gen_random_uuid(), :t, :id, 'registration', '12345678Z', :d)"
                    ),
                    {},
                ),
                (
                    (
                        "UPDATE public.invoices SET status = 'issued', issue_year = 2026, "
                        "number = 1, issue_date = :d, issued_at = :at, issuer_name = 'E', "
                        "issuer_tax_id = '12345678Z', issuer_address = 'D', recipient_name = 'C', "
                        "recipient_tax_id = 'B12345674', recipient_address = 'D' WHERE id = :id"
                    ),
                    {},
                ),
            ],
        ),
    )

    assert rejection is not None
    assert rejection.sqlstate == "KZF01", rejection
