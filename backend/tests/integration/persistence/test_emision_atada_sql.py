"""La base de datos ata la emisión al contador y a la cadena (RN-F-01, RN-F-04, RN-F-07).

Por SQL directo, sin pasar por ``IssueInvoice`` y con el rol de la app o con el
propietario, no se puede:

- crear una factura ya emitida ni marcar una como emitida sin que el contador
  de su serie llegue a su número y sin su registro de alta;
- mover el contador para dejar huecos, hacerlo retroceder o bloquear la serie;
- añadir un registro de una factura sin emitir, uno con otro número que el de
  su factura, un segundo alta que no sea subsanación, o uno que la cabeza de
  la cadena no alcance;
- citar como rectificada o como fase anterior una factura sin emitir.

Cada intento se deshace al final (``attempt``): los triggers diferidos se
adelantan con ``SET CONSTRAINTS ALL IMMEDIATE`` y nada se confirma. La emisión
por SQL que sí cumple todo está en ``test_lectura_emitidas.py``.
"""

import asyncio
from datetime import date

import pytest

from kapataz.domain.billing.numbering import DocumentNumber, Series
from tests.billing_support import add_corrective_draft, add_customer, add_draft, create_account
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import ISSUE_AT, issue_new, run_sql
from tests.integration.persistence.sql_support import attempt

ROLES = pytest.mark.parametrize("role", [APP_ROLE, OWNER_ROLE])
ISSUE_DATE = date(2026, 11, 18)  # La de ISSUE_AT en Madrid.
SERIES = Series.invoices().code

_MARK_ISSUED = (
    "UPDATE invoices SET status = 'issued', issue_year = 2026, number = :number, "
    "issue_date = :d, issued_at = :at, issuer_name = 'Reformas Ejemplo', "
    "issuer_tax_id = '12345678Z', issuer_address = 'Calle Mayor 1', "
    "recipient_name = 'Cliente Ejemplo', recipient_tax_id = 'B12345674', "
    "recipient_address = 'Avenida del Puerto 2' WHERE id = :id"
)

# Copia del último registro de la cuenta (:record), bien enlazada con él, para
# la factura :invoice. :is_correction lo marca como subsanación y
# :series_number, si no es NULL, sustituye el número de la factura.
_NEXT_RECORD = (
    "INSERT INTO billing_records SELECT (jsonb_populate_record(NULL::billing_records, "
    "to_jsonb(r) || jsonb_build_object('id', gen_random_uuid(), 'invoice_id', "
    "CAST(:invoice AS uuid), 'previous_record_id', r.id, 'is_first', false, "
    "'is_correction', CAST(:is_correction AS boolean), "
    "'prev_issuer_tax_id', r.issuer_tax_id, 'prev_series_number', r.series_number, "
    "'prev_issue_date', r.issue_date, 'prev_hash', r.hash) "
    "|| jsonb_strip_nulls(jsonb_build_object('series_number', CAST(:series_number AS text))))).* "
    "FROM billing_records r WHERE r.id = :record"
)
_ADVANCE_HEAD = (
    "UPDATE billing_chain_heads SET last_record_id = "
    "(SELECT id FROM billing_records WHERE previous_record_id = :record) WHERE tenant_id = :t"
)


def _next_record(record, invoice, *, is_correction=False, series_number=None):
    return {
        "record": record,
        "invoice": invoice,
        "is_correction": is_correction,
        "series_number": series_number,
    }


def _draft_account(factory):
    tenant_id = asyncio.run(create_account(factory))
    customer_id = asyncio.run(add_customer(factory, tenant_id))
    return tenant_id, customer_id, asyncio.run(add_draft(factory, tenant_id, customer_id))


def _expect(rejection, sqlstate, rule):
    assert rejection is not None, "La base de datos lo aceptó."
    assert rejection.sqlstate == sqlstate, rejection
    assert rejection.message.startswith(rule), rejection


# ---------------------------------------------------------------- facturas


@pytest.mark.req("RN-F-01")
@pytest.mark.owasp("A08")
@ROLES
def test_una_factura_no_se_inserta_ya_emitida(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    copy_as_number_99 = (
        "INSERT INTO invoices SELECT (jsonb_populate_record(NULL::invoices, to_jsonb(i) || "
        "jsonb_build_object('id', gen_random_uuid(), 'number', 99))).* "
        "FROM invoices i WHERE i.id = :id"
    )

    rejection = attempt(
        database, role, [(copy_as_number_99, {"id": issued.invoice.id})], tenant_id=tenant_id
    )

    _expect(rejection, "KZF01", "RN-F-01")


@pytest.mark.req("RN-F-01")
@pytest.mark.owasp("A08")
@ROLES
def test_no_se_marca_emitida_sin_tomar_el_numero_del_contador(app_factory, database, role):
    tenant_id, _, draft_id = _draft_account(app_factory)
    params = {"id": draft_id, "number": 1, "d": ISSUE_DATE, "at": ISSUE_AT}

    rejection = attempt(database, role, [(_MARK_ISSUED, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF01", "RN-F-01")


@pytest.mark.req("RN-F-01")
@pytest.mark.owasp("A08")
@ROLES
def test_no_se_marca_emitida_con_un_numero_que_no_es_el_del_contador(app_factory, database, role):
    # El contador está en 1 (la primera emitida); la segunda se marca con el 3.
    tenant_id, [issued] = issue_new(app_factory)
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, issued.invoice.customer_id))
    params = {"id": draft_id, "number": 3, "d": ISSUE_DATE, "at": ISSUE_AT}

    rejection = attempt(database, role, [(_MARK_ISSUED, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF01", "RN-F-01")


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
@ROLES
def test_no_se_marca_emitida_sin_su_registro_de_alta(app_factory, database, role):
    # Contador y factura cuadran; falta el registro.
    tenant_id, _, draft_id = _draft_account(app_factory)
    params = {
        "id": draft_id,
        "t": tenant_id,
        "series": SERIES,
        "number": 1,
        "d": ISSUE_DATE,
        "at": ISSUE_AT,
    }

    rejection = attempt(
        database,
        role,
        [
            (
                "INSERT INTO series_counters VALUES (:t, :series, 2026, 0, NULL)",
                params,
            ),
            (_MARK_ISSUED, params),
            (
                (
                    "UPDATE series_counters SET last_number = 1, last_issue_date = :d "
                    "WHERE tenant_id = :t AND series = :series AND year = 2026"
                ),
                params,
            ),
        ],
        tenant_id=tenant_id,
    )

    _expect(rejection, "KZF07", "RN-F-07")


# ---------------------------------------------------------------- contador

# El contador de la cuenta está en 1, con fecha ISSUE_DATE (una emitida).
_COUNTER = "WHERE tenant_id = :t AND series = :series AND year = 2026"
_COUNTER_CASES = {
    "salta-un-numero": (
        f"UPDATE series_counters SET last_number = 3 {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
    "bloquea-la-serie-con-el-maximo": (
        f"UPDATE series_counters SET last_number = 2147483647 {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
    "vuelve-a-cero": (
        f"UPDATE series_counters SET last_number = 0, last_issue_date = NULL {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
    "adelanta-la-fecha-sin-numero": (
        f"UPDATE series_counters SET last_issue_date = DATE '2026-12-31' {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
    "fecha-anterior": (
        (
            f"UPDATE series_counters SET last_number = 2, last_issue_date = DATE '2026-11-17' "
            f"{_COUNTER}"
        ),
        "KZF04",
        "RN-F-04",
    ),
    "fecha-de-otro-ano": (
        (
            f"UPDATE series_counters SET last_number = 2, last_issue_date = DATE '2027-01-02' "
            f"{_COUNTER}"
        ),
        "KZF01",
        "RN-F-01",
    ),
    "cambia-de-ano": (
        f"UPDATE series_counters SET year = 2025 {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
    "nace-adelantado": (
        "INSERT INTO series_counters VALUES (:t, :series, 2027, 5, DATE '2027-01-04')",
        "KZF01",
        "RN-F-01",
    ),
    # Avanza bien, pero sin la factura emitida del 2: quedaría un hueco.
    "avanza-sin-factura": (
        f"UPDATE series_counters SET last_number = 2 {_COUNTER}",
        "KZF01",
        "RN-F-01",
    ),
}


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-04")
@pytest.mark.owasp("A08")
@ROLES
@pytest.mark.parametrize(
    ("statement", "sqlstate", "rule"), _COUNTER_CASES.values(), ids=list(_COUNTER_CASES)
)
def test_el_contador_solo_avanza_con_cada_emision(
    app_factory, database, role, statement, sqlstate, rule
):
    tenant_id, [_] = issue_new(app_factory)

    rejection = attempt(
        database, role, [(statement, {"t": tenant_id, "series": SERIES})], tenant_id=tenant_id
    )

    _expect(rejection, sqlstate, rule)


# ------------------------------------------------------------------ cadena


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
@ROLES
def test_un_registro_es_siempre_de_una_factura_emitida(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, issued.invoice.customer_id))
    params = _next_record(issued.record.id, draft_id)

    rejection = attempt(database, role, [(_NEXT_RECORD, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF07", "RN-F-07")


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
@ROLES
def test_un_registro_suelto_que_la_cabeza_no_alcanza_no_se_confirma(app_factory, database, role):
    # Una subsanación bien enlazada y de una factura emitida, pero la cabeza no
    # avanza: el siguiente registro de la cuenta ya no podría enlazar sin bifurcar.
    tenant_id, [issued] = issue_new(app_factory)
    params = _next_record(issued.record.id, issued.invoice.id, is_correction=True)

    rejection = attempt(database, role, [(_NEXT_RECORD, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF07", "RN-F-07")


# --------------------------------------------------- referencias fiscales


@pytest.mark.req("RN-F-03")
@pytest.mark.owasp("A08")
@ROLES
def test_una_rectificativa_solo_cita_facturas_emitidas(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    customer_id = issued.invoice.customer_id
    corrective_id = asyncio.run(
        add_corrective_draft(app_factory, tenant_id, customer_id, issued.invoice)
    )
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, customer_id))

    rejection = attempt(
        database,
        role,
        [
            (
                (
                    "INSERT INTO invoice_corrections (tenant_id, corrective_invoice_id, "
                    "rectified_invoice_id, position) VALUES (:t, :corrective, :draft, 2)"
                ),
                {"t": tenant_id, "corrective": corrective_id, "draft": draft_id},
            )
        ],
        tenant_id=tenant_id,
    )

    _expect(rejection, "KZF03", "RN-F-03")


@pytest.mark.req("RN-F-12")
@pytest.mark.owasp("A08")
@ROLES
@pytest.mark.parametrize("operation", ["insert", "update"])
def test_una_fase_solo_descuenta_facturas_emitidas(app_factory, database, role, operation):
    tenant_id, customer_id, draft_id = _draft_account(app_factory)
    other_draft_id = asyncio.run(add_draft(app_factory, tenant_id, customer_id))
    params = {"t": tenant_id, "id": draft_id, "prior": other_draft_id}
    statement = {
        "insert": (
            "INSERT INTO invoice_lines (id, tenant_id, invoice_id, position, description, "
            "quantity, unit_price, is_material, outside_works, origin, prior_invoice_id) "
            "VALUES (gen_random_uuid(), :t, :id, 99, 'A deducir', 1, -100, false, false, "
            "'prior_invoice', :prior)"
        ),
        "update": (
            "UPDATE invoice_lines SET origin = 'prior_invoice', prior_invoice_id = :prior "
            "WHERE invoice_id = :id AND position = 1"
        ),
    }[operation]

    rejection = attempt(database, role, [(statement, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF12", "RN-F-12")


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
@ROLES
def test_un_registro_con_otro_numero_no_se_admite(app_factory, database, role):
    # Subsanación de la factura emitida F-2026-0001 que dice ser de la 0099.
    tenant_id, [issued] = issue_new(app_factory)
    params = _next_record(
        issued.record.id, issued.invoice.id, is_correction=True, series_number="F-2026-0099"
    )

    rejection = attempt(database, role, [(_NEXT_RECORD, params)], tenant_id=tenant_id)

    _expect(rejection, "KZF07", "RN-F-07")
    assert "no identifica a su factura" in rejection.message


@pytest.mark.req("RN-F-07")
@pytest.mark.owasp("A08")
@ROLES
def test_una_factura_tiene_un_solo_alta(app_factory, database, role):
    tenant_id, [issued] = issue_new(app_factory)
    params = _next_record(issued.record.id, issued.invoice.id)

    rejection = attempt(database, role, [(_NEXT_RECORD, params)], tenant_id=tenant_id)

    assert rejection is not None
    assert rejection.sqlstate == "23505", rejection  # unique_violation
    assert "uq_billing_records_registration" in rejection.message


@pytest.mark.req("RN-F-07")
@ROLES
def test_una_subsanacion_encadenada_si_se_admite(app_factory, database, role):
    # Control de las dos anteriores: con su número y marcada como subsanación,
    # y con la cabeza avanzada hasta ella, la base de datos la acepta.
    tenant_id, [issued] = issue_new(app_factory)
    params = {
        **_next_record(issued.record.id, issued.invoice.id, is_correction=True),
        "t": tenant_id,
    }

    rejection = attempt(
        database, role, [(_NEXT_RECORD, params), (_ADVANCE_HEAD, params)], tenant_id=tenant_id
    )

    assert rejection is None


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
@pytest.mark.parametrize("sequence", [1, 42, 9999, 10000, 123456])
def test_el_numero_que_compara_la_base_de_datos_es_el_del_dominio(database, sequence):
    for series in (Series.invoices(), Series.correctives()):
        rows = run_sql(
            database,
            APP_ROLE,
            "SELECT public.invoice_series_number(:series, 2026, :n)",
            {"series": series.code, "n": sequence},
        )
        assert rows == [(str(DocumentNumber(series, 2026, sequence)),)]
