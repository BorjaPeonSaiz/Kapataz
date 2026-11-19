"""Emisiones en procesos separados para las pruebas de concurrencia (RN-F-01, RN-F-04, RN-F-07).

Cada proceso hijo es un intérprete nuevo (``spawn``, lo único que hay en
Windows): su propio motor, su propia conexión a PostgreSQL y su propio
``IssueInvoice``. No comparte nada con el padre salvo los argumentos, que son
cadenas. La única coordinación posible entre emisiones es la de la base de
datos, igual que entre dos réplicas de la api, o entre la api y el worker.

Para que arranquen de verdad a la vez, cada hijo abre su conexión, espera en una
barrera y solo entonces emite. No hay ningún ``sleep``: no se espera «un rato»,
se espera a que estén todos listos.
"""

import asyncio
import multiprocessing
import queue
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.ids import InvoiceId
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from tests.integration.conftest import APP_ROLE, TestDatabase
from tests.integration.persistence.conftest import issue_use_case

# Margen para que arranquen todos los hijos (importar la app en Windows tarda) y
# para que terminen. Si se agota, la prueba falla con el motivo; no se reintenta.
START_TIMEOUT_S = 180
FINISH_TIMEOUT_S = 180


@dataclass(frozen=True, slots=True)
class Job:
    """Una emisión: qué factura de qué cuenta y con qué reloj."""

    tenant_id: UUID
    invoice_id: UUID
    at: datetime


@dataclass(frozen=True, slots=True)
class Outcome:
    """Resultado de una emisión en un hijo. ``error`` es el nombre de la excepción."""

    worker: int
    tenant_id: UUID
    invoice_id: UUID
    number: str | None = None
    record_id: UUID | None = None
    error: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def run_in_processes(database: TestDatabase, plan: list[list[Job]]) -> list[Outcome]:
    """Lanza un proceso por elemento de ``plan`` y devuelve todos los resultados.

    Cada proceso emite sus trabajos en orden, uno tras otro, después de la
    barrera común. Falla si algún proceso no llega a la barrera, no termina o
    sale con un código distinto de 0.
    """
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(len(plan))
    results: Any = context.Queue()
    url = database.urls[APP_ROLE].render_as_string(hide_password=False)
    processes = [
        context.Process(
            target=_child,
            args=(
                index,
                url,
                database.set_role,
                [(str(j.tenant_id), str(j.invoice_id), j.at.isoformat()) for j in jobs],
                barrier,
                results,
            ),
            name=f"emision-{index}",
        )
        for index, jobs in enumerate(plan)
    ]
    for process in processes:
        process.start()

    expected = sum(len(jobs) for jobs in plan)
    outcomes: list[Outcome] = []
    try:
        while len(outcomes) < expected:
            try:
                outcomes.append(results.get(timeout=START_TIMEOUT_S + FINISH_TIMEOUT_S))
            except queue.Empty:
                msg = f"Solo llegaron {len(outcomes)} de {expected} resultados."
                raise AssertionError(msg) from None
    finally:
        for process in processes:
            process.join(timeout=FINISH_TIMEOUT_S)
            if process.is_alive():
                process.kill()
                process.join()
    codes = {process.name: process.exitcode for process in processes}
    assert set(codes.values()) == {0}, f"Procesos que no acabaron bien: {codes}"
    return outcomes


def _child(
    worker: int,
    url: str,
    set_role: bool,
    jobs: list[tuple[str, str, str]],
    barrier: Any,
    results: Any,
) -> None:
    for outcome in asyncio.run(_issue_all(worker, url, set_role, jobs, barrier)):
        results.put(outcome)


async def _issue_all(
    worker: int, url: str, set_role: bool, jobs: list[tuple[str, str, str]], barrier: Any
) -> list[Outcome]:
    server_settings = {"application_name": f"kapataz-tests-{worker}"}
    if set_role:
        server_settings["role"] = APP_ROLE
    # Un pool de una conexión: se abre antes de la barrera y la reutilizan
    # todas las emisiones del hijo, así conectar no desincroniza a nadie.
    engine = create_async_engine(
        url, connect_args={"server_settings": server_settings}, pool_size=1, max_overflow=0
    )
    outcomes: list[Outcome] = []
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        factory = SqlAlchemyUnitOfWorkFactory(engine)
        barrier.wait(timeout=START_TIMEOUT_S)
        for tenant, invoice, at in jobs:
            outcomes.append(await _issue_one(worker, factory, UUID(tenant), UUID(invoice), at))
    finally:
        await engine.dispose()
    return outcomes


async def _issue_one(
    worker: int, factory: SqlAlchemyUnitOfWorkFactory, tenant: UUID, invoice: UUID, at: str
) -> Outcome:
    use_case = issue_use_case(factory, datetime.fromisoformat(at))
    try:
        issued = await use_case.execute(TenantId(tenant), InvoiceId(invoice))
    except Exception as error:  # noqa: BLE001 - el padre decide qué error es el esperado
        return Outcome(worker, tenant, invoice, error=type(error).__name__, message=str(error))
    return Outcome(
        worker, tenant, invoice, number=str(issued.invoice.number), record_id=issued.record.id
    )
