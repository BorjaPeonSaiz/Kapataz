"""Emisión de extremo a extremo contra PostgreSQL real (arquitectura §7)."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from kapataz.domain.billing.billing_record import verify_chain
from kapataz.domain.billing.errors import IssueDateBeforeLastError, MissingIssueDataError
from kapataz.domain.billing.numbering import Series
from tests.billing_support import (
    add_customer,
    add_draft,
    create_account,
    issuable_drafts,
)
from tests.integration.conftest import OWNER_ROLE
from tests.integration.persistence.conftest import ISSUE_AT, issue_new, issue_use_case, run_sql


def _chain(factory, tenant_id):
    async def read():
        async with factory() as uow:
            await uow.set_tenant(tenant_id)
            return await uow.billing_chain.list_chain()

    return asyncio.run(read())


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
@pytest.mark.req("RN-01")
def test_emision_guarda_factura_contador_registro_y_cabeza(app_factory, database):
    tenant_id, [first, second] = issue_new(app_factory, 2)

    assert [str(i.invoice.number) for i in (first, second)] == ["F-2026-0001", "F-2026-0002"]
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT status, series, issue_year, number, issue_date, base_total, tax_total, "
        "total_amount, amount_due, issuer_tax_id, recipient_tax_id "
        "FROM invoices WHERE tenant_id = :t ORDER BY number",
        {"t": tenant_id},
    )
    assert [tuple(row) for row in rows] == [
        (
            "issued",
            "F",
            2026,
            n,
            date(2026, 11, 18),
            125000,
            26250,
            151250,
            151250,
            "12345678Z",
            "B12345674",
        )
        for n in (1, 2)
    ]
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT last_number, last_issue_date FROM series_counters WHERE tenant_id = :t",
        {"t": tenant_id},
    ) == [(2, date(2026, 11, 18))]

    records = run_sql(
        database,
        OWNER_ROLE,
        "SELECT id, previous_record_id, is_first, canonical_json, hash, prev_hash "
        "FROM billing_records WHERE tenant_id = :t ORDER BY is_first DESC",
        {"t": tenant_id},
    )
    (first_row, second_row) = records
    # Contenido y huella guardados tal como los produjo el dominio.
    assert first_row.canonical_json == first.record.canonical_json
    assert first_row.hash == first.record.hash
    assert second_row.prev_hash == first.record.hash
    assert second_row.previous_record_id == first.record.id
    assert json.loads(second_row.canonical_json)["ImporteTotal"] == "1512.50"
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT last_record_id FROM billing_chain_heads WHERE tenant_id = :t",
        {"t": tenant_id},
    ) == [(second.record.id,)]

    chain = _chain(app_factory, tenant_id)
    assert chain == (first.record, second.record)
    verify_chain(chain)


@pytest.mark.req("RN-F-07")
def test_series_distintas_comparten_la_cadena_de_la_cuenta(app_factory):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    drafts = [
        asyncio.run(add_draft(app_factory, tenant_id, customer_id, series=series))
        for series in (Series.invoices(), Series("OBRA"), Series.invoices())
    ]
    use_case = issue_use_case(app_factory)

    issued = [asyncio.run(use_case.execute(tenant_id, draft)) for draft in drafts]

    assert [str(i.invoice.number) for i in issued] == [
        "F-2026-0001",
        "OBRA-2026-0001",
        "F-2026-0002",
    ]
    chain = _chain(app_factory, tenant_id)
    assert chain == tuple(i.record for i in issued)
    verify_chain(chain)


@pytest.mark.req("RN-F-04")
@pytest.mark.req("RN-F-01")
def test_fecha_anterior_deshace_todo_en_la_base_de_datos(app_factory, database):
    tenant_id, [first, second] = asyncio.run(issuable_drafts(app_factory, 2))
    asyncio.run(issue_use_case(app_factory).execute(tenant_id, first))
    earlier = issue_use_case(app_factory, ISSUE_AT - timedelta(days=1))

    with pytest.raises(IssueDateBeforeLastError):
        asyncio.run(earlier.execute(tenant_id, second))

    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT status FROM invoices WHERE id = :id",
        {"id": second},
    ) == [("draft",)]
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT last_number FROM series_counters WHERE tenant_id = :t",
        {"t": tenant_id},
    ) == [(1,)]
    assert len(_chain(app_factory, tenant_id)) == 1


@pytest.mark.req("RN-F-06")
def test_datos_que_faltan_no_dejan_rastro(app_factory, database):
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id, address=None))
    draft_id = asyncio.run(add_draft(app_factory, tenant_id, customer_id))

    with pytest.raises(MissingIssueDataError) as error:
        asyncio.run(issue_use_case(app_factory).execute(tenant_id, draft_id))

    assert error.value.missing == ("recipient_address",)
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT count(*) FROM billing_records WHERE tenant_id = :t",
        {"t": tenant_id},
    ) == [(0,)]


@pytest.mark.req("RN-F-01")
def test_cambio_de_ano_empieza_en_uno(app_factory):
    tenant_id, [december, january] = asyncio.run(issuable_drafts(app_factory, 2))
    asyncio.run(issue_use_case(app_factory).execute(tenant_id, december))
    new_year = issue_use_case(app_factory, datetime(2027, 1, 1, 8, 0, tzinfo=UTC))

    issued = asyncio.run(new_year.execute(tenant_id, january))

    assert str(issued.invoice.number) == "F-2027-0001"
    assert issued.record.previous is not None
