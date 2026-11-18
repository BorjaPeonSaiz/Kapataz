"""Emisiones simultáneas desde procesos distintos, contra PostgreSQL real (RN-F-01, 04 y 07).

Cada emisión corre en su propio proceso, con su propia conexión, y todas
arrancan a la vez tras una barrera (``concurrency_support``). El orden en que
la base de datos las atiende cambia de una ejecución a otra; lo que se
comprueba es lo que no puede cambiar:

- la numeración de cada cuenta, serie y año es 1, 2, 3… sin huecos ni
  duplicados (RN-F-01);
- la cadena de registros de cada cuenta es una sola, sin ramas, y
  ``verify_chain`` la da por buena leída de la base de datos (RN-F-07);
- en el orden de la cadena, que es el orden en que se confirmaron las
  emisiones, la fecha de expedición de una serie nunca retrocede (RN-F-04).

Sobre RN-F-04 y el reloj: ``IssueInvoice`` lee el ``Clock`` con la cabeza de
la cadena ya bloqueada, así que con un único reloj real las emisiones de una
cuenta leen la hora en el mismo orden en que se confirman y la fecha no puede
retroceder. El riesgo real es el desfase entre relojes de procesos distintos
(la api y el worker en contenedores o máquinas diferentes, o un ajuste de NTP
hacia atrás). Eso es lo que se simula: cada proceso con su ``FrozenClock``, unos
un día por detrás de otros. No falsea el escenario; lo provoca.
"""

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from kapataz.domain.billing.billing_record import BillingRecord, verify_chain
from kapataz.domain.billing.numbering import DocumentNumber, Series
from tests.billing_support import (
    add_corrective_draft,
    add_customer,
    add_draft,
    create_account,
    issuable_drafts,
)
from tests.integration.conftest import OWNER_ROLE
from tests.integration.persistence.concurrency_support import Job, Outcome, run_in_processes
from tests.integration.persistence.conftest import ISSUE_AT, issue_use_case, run_sql

PROCESSES = 20


# ------------------------------------------------------------------ apoyo


def _chain(factory, tenant_id) -> tuple[BillingRecord, ...]:
    async def read():
        async with factory() as uow:
            await uow.set_tenant(tenant_id)
            return await uow.billing_chain.list_chain()

    return asyncio.run(read())


def _assert_single_chain(app_factory, database, tenant_id, length) -> tuple[BillingRecord, ...]:
    """Una sola cadena, sin ramas ni registros sueltos, y válida según el dominio."""
    chain = _chain(app_factory, tenant_id)
    verify_chain(chain)
    assert len(chain) == length
    [(total, firsts, linked, distinct_links, head)] = run_sql(
        database,
        OWNER_ROLE,
        "SELECT count(*), count(*) FILTER (WHERE previous_record_id IS NULL), "
        "count(previous_record_id), count(DISTINCT previous_record_id), "
        "(SELECT last_record_id FROM billing_chain_heads WHERE tenant_id = :t) "
        "FROM billing_records WHERE tenant_id = :t",
        {"t": tenant_id},
    )
    # Todos los registros de la base de datos están en la cadena que sale de la
    # cabeza: si hubiera una rama, sobrarían registros.
    assert total == length
    # Un solo registro sin anterior por cuenta, y ningún anterior repetido.
    assert firsts == 1
    assert distinct_links == linked == length - 1
    assert head == chain[-1].id
    return chain


def _issued_numbers(database, tenant_id) -> dict[tuple[str, int], list[int]]:
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT series, issue_year, number FROM invoices "
        "WHERE tenant_id = :t AND status = 'issued' ORDER BY series, issue_year, number",
        {"t": tenant_id},
    )
    numbers: dict[tuple[str, int], list[int]] = defaultdict(list)
    for series, year, number in rows:
        numbers[(series, year)].append(number)
    return dict(numbers)


def _counters(database, tenant_id) -> dict[tuple[str, int], tuple[int, date | None]]:
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT series, year, last_number, last_issue_date FROM series_counters "
        "WHERE tenant_id = :t",
        {"t": tenant_id},
    )
    return {(series, year): (last, last_date) for series, year, last, last_date in rows}


def _assert_no_errors(outcomes: list[Outcome]) -> None:
    errors = [(o.error, o.message) for o in outcomes if not o.ok]
    assert errors == []


def _one_job_per_process(tenant_id, drafts, at: datetime = ISSUE_AT) -> list[list[Job]]:
    return [[Job(tenant_id, draft, at)] for draft in drafts]


def _f(year: int, *numbers: int) -> list[str]:
    return [str(DocumentNumber(Series.invoices(), year, n)) for n in numbers]


def _drafts_left(database, tenant_id) -> set[UUID]:
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT id FROM invoices WHERE tenant_id = :t AND status = 'draft'",
        {"t": tenant_id},
    )
    return {row[0] for row in rows}


# ----------------------------------------------------------------- pruebas


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
def test_veinte_procesos_en_una_cuenta_sin_huecos_ni_duplicados(app_factory, database):
    tenant_id, drafts = asyncio.run(issuable_drafts(app_factory, PROCESSES))

    outcomes = run_in_processes(database, _one_job_per_process(tenant_id, drafts))

    _assert_no_errors(outcomes)
    assert sorted(o.number for o in outcomes) == _f(2026, *range(1, PROCESSES + 1))
    assert _issued_numbers(database, tenant_id) == {("F", 2026): list(range(1, PROCESSES + 1))}
    assert _counters(database, tenant_id) == {("F", 2026): (PROCESSES, date(2026, 11, 18))}
    chain = _assert_single_chain(app_factory, database, tenant_id, PROCESSES)
    # Cada factura tiene su registro, y el orden de la cadena es el de los números.
    assert {r.invoice_id for r in chain} == set(drafts)
    assert {r.id for r in chain} == {o.record_id for o in outcomes}
    assert [r.series_number for r in chain] == _f(2026, *range(1, PROCESSES + 1))


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-07")
@pytest.mark.req("RN-10")
def test_varias_cuentas_a_la_vez_cada_una_con_su_numeracion_y_su_cadena(app_factory, database):
    accounts = [asyncio.run(issuable_drafts(app_factory, PROCESSES)) for _ in range(3)]
    # Cada proceso emite una factura de cada cuenta, empezando por una distinta:
    # las tres cuentas reciben a la vez veinte emisiones simultáneas.
    plan = [
        [
            Job(accounts[(index + shift) % 3][0], accounts[(index + shift) % 3][1][index], ISSUE_AT)
            for shift in range(3)
        ]
        for index in range(PROCESSES)
    ]

    outcomes = run_in_processes(database, plan)

    _assert_no_errors(outcomes)
    assert len(outcomes) == 3 * PROCESSES
    for tenant_id, drafts in accounts:
        mine = [o for o in outcomes if o.tenant_id == tenant_id]
        assert {o.invoice_id for o in mine} == set(drafts)
        assert sorted(o.number for o in mine) == _f(2026, *range(1, PROCESSES + 1))
        assert _issued_numbers(database, tenant_id) == {("F", 2026): list(range(1, PROCESSES + 1))}
        assert _counters(database, tenant_id) == {("F", 2026): (PROCESSES, date(2026, 11, 18))}
        chain = _assert_single_chain(app_factory, database, tenant_id, PROCESSES)
        assert {r.invoice_id for r in chain} == set(drafts)


@pytest.mark.req("RN-F-07")
@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-03")
def test_series_f_y_r_simultaneas_no_bifurcan_la_cadena(app_factory, database):
    half = PROCESSES // 2
    tenant_id = asyncio.run(create_account(app_factory))
    customer_id = asyncio.run(add_customer(app_factory, tenant_id))
    # Facturas ya emitidas, una a una, que se van a rectificar.
    use_case = issue_use_case(app_factory)
    rectified = []
    for _ in range(half):
        draft = asyncio.run(add_draft(app_factory, tenant_id, customer_id))
        rectified.append(asyncio.run(use_case.execute(tenant_id, draft)).invoice)
    correctives = [
        asyncio.run(add_corrective_draft(app_factory, tenant_id, customer_id, invoice))
        for invoice in rectified
    ]
    invoices = [asyncio.run(add_draft(app_factory, tenant_id, customer_id)) for _ in range(half)]
    # F y R alternas, para que se crucen desde el primer momento.
    drafts = [draft for pair in zip(invoices, correctives, strict=True) for draft in pair]

    outcomes = run_in_processes(database, _one_job_per_process(tenant_id, drafts))

    _assert_no_errors(outcomes)
    assert _issued_numbers(database, tenant_id) == {
        ("F", 2026): list(range(1, 2 * half + 1)),
        ("R", 2026): list(range(1, half + 1)),
    }
    chain = _assert_single_chain(app_factory, database, tenant_id, 3 * half)
    assert [r.invoice_id for r in chain[:half]] == [i.id for i in rectified]
    assert {r.invoice_id for r in chain[half:]} == set(drafts)
    # Dentro de la cadena común, cada serie conserva su orden.
    for prefix in ("F-", "R-"):
        in_series = [r.series_number for r in chain if r.series_number.startswith(prefix)]
        assert in_series == sorted(in_series)
    # Cada rectificativa emitida sigue citando su factura.
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT count(*) FROM invoice_corrections c JOIN invoices i "
        "ON i.tenant_id = c.tenant_id AND i.id = c.corrective_invoice_id "
        "WHERE c.tenant_id = :t AND i.status = 'issued' AND i.series = 'R'",
        {"t": tenant_id},
    ) == [(half,)]


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-F-02")
def test_la_misma_factura_a_la_vez_se_emite_una_vez_sin_consumir_numero(app_factory, database):
    contenders = 10
    tenant_id, [draft, later] = asyncio.run(issuable_drafts(app_factory, 2))

    outcomes = run_in_processes(
        database, [[Job(tenant_id, draft, ISSUE_AT)] for _ in range(contenders)]
    )

    assert Counter(o.error for o in outcomes) == {
        None: 1,
        "InvoiceAlreadyIssuedError": contenders - 1,
    }
    [winner] = [o for o in outcomes if o.ok]
    assert winner.number == "F-2026-0001"
    assert _counters(database, tenant_id) == {("F", 2026): (1, date(2026, 11, 18))}
    _assert_single_chain(app_factory, database, tenant_id, 1)
    # Las que fallaron no consumieron número: la siguiente es la 2.
    issued = asyncio.run(issue_use_case(app_factory).execute(tenant_id, later))
    assert str(issued.invoice.number) == "F-2026-0002"


@pytest.mark.req("RN-F-04")
@pytest.mark.req("RN-F-01")
@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        pytest.param(ISSUE_AT, ISSUE_AT + timedelta(days=1), id="mismo-anio"),
        pytest.param(
            datetime(2026, 12, 31, 12, 0, tzinfo=UTC),
            datetime(2027, 1, 1, 12, 0, tzinfo=UTC),
            id="cambio-de-anio",
        ),
    ],
)
def test_relojes_desfasados_nunca_dejan_una_fecha_anterior(app_factory, database, earlier, later):
    tenant_id, drafts = asyncio.run(issuable_drafts(app_factory, PROCESSES))
    # La mitad de los procesos, alternos, va un día por detrás.
    plan = [[Job(tenant_id, draft, later if i % 2 else earlier)] for i, draft in enumerate(drafts)]

    outcomes = run_in_processes(database, plan)

    late = {draft for i, draft in enumerate(drafts) if i % 2}
    issued = [o for o in outcomes if o.ok]
    rejected = [o for o in outcomes if not o.ok]
    # Las del día posterior se emiten siempre; las del anterior, solo si llegan
    # antes que cualquiera del posterior. Ningún otro error.
    assert all(o.ok for o in outcomes if o.invoice_id in late)
    assert {o.error for o in rejected} <= {"IssueDateBeforeLastError"}
    # Lo rechazado se deshace entero: sigue en borrador y no gasta número.
    assert _drafts_left(database, tenant_id) == {o.invoice_id for o in rejected}
    numbers = _issued_numbers(database, tenant_id)
    for year_numbers in numbers.values():
        assert year_numbers == list(range(1, len(year_numbers) + 1))
    assert sum(len(n) for n in numbers.values()) == len(issued)
    assert sum(last for last, _ in _counters(database, tenant_id).values()) == len(issued)
    # En el orden en que se confirmaron (el de la cadena), la fecha no retrocede.
    chain = _assert_single_chain(app_factory, database, tenant_id, len(issued))
    dates = [r.issue_date for r in chain]
    assert dates == sorted(dates)
