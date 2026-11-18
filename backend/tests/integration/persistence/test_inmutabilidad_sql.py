"""Inmutabilidad en la base de datos, por SQL directo y sin pasar por el código (RN-F-02, RN-F-07).

Los triggers actúan también para el propietario de las tablas, no solo para el
rol de la app.
"""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.billing_support import add_corrective_draft, add_customer, add_draft, create_account
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import issue_new, issue_use_case, run_sql

ROLES = pytest.mark.parametrize("role", [APP_ROLE, OWNER_ROLE])


@pytest.mark.req("RN-F-02")
@pytest.mark.owasp("A08")
@ROLES
def test_update_de_una_factura_emitida_falla_por_el_trigger(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)

    for statement in (
        "UPDATE invoices SET description = 'Cambiada' WHERE id = :id",
        (
            "UPDATE invoices SET total_amount = 1, base_total = 1, tax_total = 0, amount_due = 1 "
            "WHERE id = :id"
        ),
        "UPDATE invoices SET status = 'draft', number = NULL WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="RN-F-02"):
            run_sql(database, role, statement, {"id": issued.invoice.id}, tenant_id=tenant_id)

    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT description FROM invoices WHERE id = :id",
        {"id": issued.invoice.id},
    )
    assert rows == [("Reforma de baño",)]


@pytest.mark.req("RN-F-02")
@ROLES
def test_delete_de_una_factura_emitida_falla_por_el_trigger(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)

    with pytest.raises(DBAPIError, match="RN-F-02"):
        run_sql(
            database,
            role,
            "DELETE FROM invoices WHERE id = :id",
            {"id": issued.invoice.id},
            tenant_id=tenant_id,
        )


@pytest.mark.req("RN-F-02")
@ROLES
def test_las_lineas_de_una_factura_emitida_no_cambian(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    params = {"id": issued.invoice.id, "t": tenant_id, "line": uuid4()}

    for statement in (
        "UPDATE invoice_lines SET unit_price = 1 WHERE invoice_id = :id",
        "DELETE FROM invoice_lines WHERE invoice_id = :id",
        (
            "INSERT INTO invoice_lines (id, tenant_id, invoice_id, position, description, "
            "quantity, unit_price, is_material, outside_works) "
            "VALUES (:line, :t, :id, 99, 'Añadida', 1, 100, false, false)"
        ),
    ):
        with pytest.raises(DBAPIError, match="RN-F-02"):
            run_sql(database, role, statement, params, tenant_id=tenant_id)


@pytest.mark.req("RN-F-02")
def test_un_borrador_si_se_edita_y_se_borra_con_sus_lineas(app_factory, database):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, customer_id))

    run_sql(
        database,
        APP_ROLE,
        "UPDATE invoices SET description = 'Otra' WHERE id = :id",
        {"id": draft_id},
        tenant_id=tenant_id,
    )
    run_sql(
        database,
        APP_ROLE,
        "DELETE FROM invoices WHERE id = :id",
        {"id": draft_id},
        tenant_id=tenant_id,
    )

    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT count(*) FROM invoice_lines WHERE invoice_id = :id",
        {"id": draft_id},
    ) == [(0,)]


@pytest.mark.req("RN-F-03")
@pytest.mark.req("RN-F-02")
def test_no_se_anade_lo_rectificado_a_una_rectificativa_emitida(app_factory, database):
    # Como propietario, sin RLS ni permisos de por medio: lo para el trigger.
    tenant_id, [issued, other] = issue_new(app_factory, 2)

    with pytest.raises(DBAPIError, match="RN-F-02"):
        run_sql(
            database,
            OWNER_ROLE,
            "INSERT INTO invoice_corrections (tenant_id, corrective_invoice_id, "
            "rectified_invoice_id, position) VALUES (:t, :corrective, :rectified, 1)",
            {"t": tenant_id, "corrective": issued.invoice.id, "rectified": other.invoice.id},
        )


@pytest.mark.req("RN-F-07")
@ROLES
def test_un_registro_solo_cambia_en_las_columnas_de_envio(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    record_id = {"id": issued.record.id}

    for statement in (
        "UPDATE billing_records SET hash = repeat('A', 64) WHERE id = :id",
        "UPDATE billing_records SET canonical_json = '{}' WHERE id = :id",
        "UPDATE billing_records SET series_number = 'F-2026-0099' WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="RN-F-07"):
            run_sql(database, role, statement, record_id, tenant_id=tenant_id)

    run_sql(
        database,
        role,
        "UPDATE billing_records SET submission_status = 'accepted', submission_csv = 'CSV1', "
        "submitted_at = now(), error_code = NULL, error_description = NULL, "
        "sent_with_incident = true WHERE id = :id",
        record_id,
        tenant_id=tenant_id,
    )
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT submission_status, hash FROM billing_records WHERE id = :id",
        record_id,
    ) == [("accepted", issued.record.hash)]


@pytest.mark.req("RN-F-07")
def test_un_registro_no_se_borra_ni_como_propietario(app_factory, database):
    tenant_id, [issued] = issue_new(app_factory)

    with pytest.raises(DBAPIError, match="RN-F-07"):
        run_sql(
            database,
            OWNER_ROLE,
            "DELETE FROM billing_records WHERE id = :id",
            {"id": issued.record.id},
        )
    with pytest.raises(DBAPIError, match="permission denied"):
        run_sql(
            database,
            APP_ROLE,
            "DELETE FROM billing_records WHERE id = :id",
            {"id": issued.record.id},
            tenant_id=tenant_id,
        )


@pytest.mark.req("RN-F-02")
@pytest.mark.parametrize(
    "table", ["invoices", "invoice_lines", "invoice_corrections", "billing_records"]
)
def test_las_tablas_fiscales_no_se_vacian(database, table):
    with pytest.raises(DBAPIError, match="RN-F-02"):
        run_sql(database, OWNER_ROLE, f"TRUNCATE {table} CASCADE")


@pytest.mark.req("RN-F-07")
def test_la_cadena_no_se_bifurca_ni_admite_enlaces_falsos(app_factory, database):
    tenant_id, [first, second] = issue_new(app_factory, 2)
    columns = (
        "id, tenant_id, invoice_id, previous_record_id, record_type, is_correction, "
        "prior_rejection, issuer_tax_id, series_number, issue_date, is_first, prev_issuer_tax_id, "
        "prev_series_number, prev_issue_date, prev_hash, system_name, system_id, system_version, "
        "installation_number, generated_at, external_ref, canonical_json, hash, "
        "submission_status, error_code, error_description, submission_csv, submitted_at, "
        "sent_with_incident"
    )
    copy_of_second = (
        f"INSERT INTO billing_records ({columns}) SELECT :new_id, tenant_id, invoice_id, "
        f"previous_record_id, record_type, is_correction, prior_rejection, issuer_tax_id, "
        f"series_number, issue_date, is_first, prev_issuer_tax_id, prev_series_number, "
        f"prev_issue_date, {{prev_hash}}, system_name, system_id, system_version, "
        f"installation_number, generated_at, external_ref, canonical_json, hash, "
        f"submission_status, error_code, error_description, submission_csv, submitted_at, "
        f"sent_with_incident FROM billing_records WHERE id = :id"
    )
    params = {"new_id": uuid4(), "id": second.record.id}

    # Otro registro detrás del primero: la cadena se bifurcaría.
    with pytest.raises(DBAPIError, match="uq_billing_records_previous"):
        run_sql(database, OWNER_ROLE, copy_of_second.format(prev_hash="prev_hash"), params)
    # Un enlace que no copia la huella del anterior.
    with pytest.raises(DBAPIError, match="RN-F-07"):
        run_sql(database, OWNER_ROLE, copy_of_second.format(prev_hash="repeat('B', 64)"), params)
    # La cabeza no vuelve atrás ni salta.
    with pytest.raises(DBAPIError, match="RN-F-07"):
        run_sql(
            database,
            APP_ROLE,
            "UPDATE billing_chain_heads SET last_record_id = :id WHERE tenant_id = :t",
            {"id": first.record.id, "t": tenant_id},
            tenant_id=tenant_id,
        )


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-02")
@pytest.mark.owasp("A01")
def test_el_rol_de_la_app_no_borra_lo_que_no_debe(database):
    rows = run_sql(
        database,
        APP_ROLE,
        "SELECT t, has_table_privilege(current_user, t, 'DELETE') "
        "FROM unnest(ARRAY['billing_records', 'invoice_corrections', 'series_counters', "
        "'billing_chain_heads', 'payments', 'invoices', 'invoice_lines']) AS t",
    )
    assert dict(rows) == {
        "billing_records": False,
        "invoice_corrections": False,
        "series_counters": False,
        "billing_chain_heads": False,
        "payments": False,
        # Solo para borradores: el trigger impide borrar una emitida.
        "invoices": True,
        "invoice_lines": True,
    }


# ------------------------------------------- columna a columna, por el catálogo

# Columnas de billing_records que el envío puede cambiar (migración 0003).
SUBMISSION_COLUMNS = frozenset(
    {
        "submission_status",
        "error_code",
        "error_description",
        "submission_csv",
        "submitted_at",
        "sent_with_incident",
    }
)

# Un valor distinto del actual para cada tipo, también si es NULL. Los textos,
# de una sola letra: un valor más largo que la columna fallaría antes de llegar
# al trigger y la prueba no comprobaría nada.
_DIFFERENT = {
    "uuid": "gen_random_uuid()",
    "character varying": "CASE WHEN {c} = 'x' THEN 'y' ELSE 'x' END",
    "text": "CASE WHEN {c} = 'x' THEN 'y' ELSE 'x' END",
    "integer": "COALESCE({c}, 0) + 1",
    "smallint": "COALESCE({c}, 0) + 1",
    "numeric": "COALESCE({c}, 0) + 1",
    "boolean": "NOT COALESCE({c}, false)",
    "date": "COALESCE({c}, DATE '2026-01-01') + 1",
    "timestamp with time zone": "COALESCE({c}, now()) + interval '1 day'",
}


def _probe_columns(database, role, table, where, params, *, tenant_id, code):
    """Intenta cambiar cada columna de una fila, una a una, y al final lo deshace todo.

    Devuelve, por columna, ``"trigger"`` si la rechazó el trigger con ``code``,
    ``"cambia"`` si el trigger la dejó pasar, o el error si falló por otra cosa.
    Las columnas salen del catálogo: una columna nueva queda cubierta sin tocar
    la prueba. Los triggers BEFORE se ejecutan antes que RLS (WITH CHECK) y que
    las restricciones, así que el veredicto es el del trigger.
    """
    columns = run_sql(
        database,
        OWNER_ROLE,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table ORDER BY ordinal_position",
        {"table": table},
    )
    assert columns, table

    async def probe() -> dict[str, str]:
        engine = database.engine(role)
        verdicts: dict[str, str] = {}
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                if tenant_id is not None:
                    await conn.execute(
                        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
                    )
                for column, data_type in columns:
                    value = _DIFFERENT[data_type].format(c=column)
                    statement = text(f"UPDATE {table} SET {column} = {value} WHERE {where}")
                    try:
                        async with conn.begin_nested():
                            result = await conn.execute(statement, dict(params))
                            assert result.rowcount == 1, (column, result.rowcount)
                            verdicts[column] = "cambia"
                    except DBAPIError as error:
                        verdicts[column] = "trigger" if code in str(error) else str(error.orig)
                await transaction.rollback()
        finally:
            await engine.dispose()
        return verdicts

    return asyncio.run(probe())


@pytest.mark.req("RN-F-02")
@pytest.mark.owasp("A08")
@ROLES
def test_ninguna_columna_de_una_factura_emitida_cambia(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)

    verdicts = _probe_columns(
        database,
        role,
        "invoices",
        "id = :id",
        {"id": issued.invoice.id},
        tenant_id=tenant_id,
        code="RN-F-02",
    )

    assert verdicts == dict.fromkeys(verdicts, "trigger")


@pytest.mark.req("RN-F-02")
@ROLES
def test_ninguna_columna_de_una_linea_emitida_cambia(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)

    verdicts = _probe_columns(
        database,
        role,
        "invoice_lines",
        "invoice_id = :id AND position = 1",
        {"id": issued.invoice.id},
        tenant_id=tenant_id,
        code="RN-F-02",
    )

    assert verdicts == dict.fromkeys(verdicts, "trigger")


@pytest.mark.req("RN-F-07")
@ROLES
def test_de_un_registro_solo_cambian_las_columnas_de_envio(app_factory, database, role):
    tenant_id, [_, issued] = issue_new(app_factory, 2)  # El segundo, enlazado al primero.

    verdicts = _probe_columns(
        database,
        role,
        "billing_records",
        "id = :id",
        {"id": issued.record.id},
        tenant_id=tenant_id,
        code="RN-F-07",
    )

    # Las de envío pasan el trigger; que después una restricción CHECK rechace
    # un valor de prueba como 'x' no es asunto de RN-F-07.
    passed = {column for column, verdict in verdicts.items() if verdict != "trigger"}
    assert passed == SUBMISSION_COLUMNS


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RN-F-03")
def test_lo_rectificado_por_una_rectificativa_emitida_no_cambia(app_factory, database):
    tenant_id, [original] = issue_new(app_factory)
    corrective_id = asyncio.run(
        add_corrective_draft(app_factory, tenant_id, original.invoice.customer_id, original.invoice)
    )
    asyncio.run(issue_use_case(app_factory).execute(tenant_id, corrective_id))
    where = "corrective_invoice_id = :id"
    params = {"id": corrective_id}

    # Al propietario lo para el trigger, columna a columna y al borrar.
    verdicts = _probe_columns(
        database, OWNER_ROLE, "invoice_corrections", where, params, tenant_id=None, code="RN-F-02"
    )
    assert verdicts == dict.fromkeys(verdicts, "trigger")
    with pytest.raises(DBAPIError, match="RN-F-02"):
        run_sql(database, OWNER_ROLE, f"DELETE FROM invoice_corrections WHERE {where}", params)
    # La app ni siquiera tiene permiso.
    for statement in (
        f"UPDATE invoice_corrections SET position = 2 WHERE {where}",
        f"DELETE FROM invoice_corrections WHERE {where}",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            run_sql(database, APP_ROLE, statement, params, tenant_id=tenant_id)
    assert run_sql(
        database, OWNER_ROLE, f"SELECT count(*) FROM invoice_corrections WHERE {where}", params
    ) == [(1,)]


@pytest.mark.req("RN-F-02")
@pytest.mark.owasp("A01")
def test_el_rol_de_la_app_no_vacia_ninguna_tabla(database):
    rows = run_sql(
        database,
        APP_ROLE,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
        "AND has_table_privilege(current_user, c.oid, 'TRUNCATE')",
    )
    assert rows == []
    with pytest.raises(DBAPIError, match="permission denied"):
        run_sql(database, APP_ROLE, "TRUNCATE invoices CASCADE")


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
def test_sin_contador_ni_cabeza_la_base_de_datos_no_duplica_ni_bifurca(app_factory, database):
    # series_counters y billing_chain_heads no tienen el trigger de TRUNCATE. Si
    # el propietario los vaciara, la base de datos seguiría sin admitir un número
    # repetido ni un segundo primer registro: no depende solo de ellos. Todo
    # ocurre en una transacción que se deshace al final.
    tenant_id, [issued] = issue_new(app_factory)
    duplicate = (
        "INSERT INTO {table} SELECT (jsonb_populate_record(NULL::{table}, "
        "to_jsonb(t) || jsonb_build_object('id', gen_random_uuid()))).* "
        "FROM {table} t WHERE id = :id"
    )

    async def scenario() -> list[str]:
        engine = database.engine(OWNER_ROLE)
        errors: list[str] = []
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                await conn.execute(text("TRUNCATE series_counters, billing_chain_heads"))
                for table, row_id in (
                    ("invoices", issued.invoice.id),
                    ("billing_records", issued.record.id),
                ):
                    try:
                        async with conn.begin_nested():
                            await conn.execute(text(duplicate.format(table=table)), {"id": row_id})
                    except DBAPIError as error:
                        errors.append(str(error.orig))
                await transaction.rollback()
        finally:
            await engine.dispose()
        return errors

    numbers, records = asyncio.run(scenario())
    assert "uq_invoices_number" in numbers
    assert "uq_billing_records_previous" in records
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT last_number FROM series_counters WHERE tenant_id = :t",
        {"t": tenant_id},
    ) == [(1,)]
