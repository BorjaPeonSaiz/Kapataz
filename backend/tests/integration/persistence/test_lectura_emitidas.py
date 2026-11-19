"""Lectura de facturas emitidas contra PostgreSQL real (RN-F-02).

Una factura emitida antes de que se endurezca una regla de emisión tiene que
seguir leyéndose. Para tener una así sin esperar a que cambie la normativa, la
prueba emite por SQL, con el rol de la app y en una sola transacción, lo mismo
que haría ``IssueInvoice``: la factura pasa a emitida con el número 1, el
contador avanza hasta ella y su registro de alta entra en la cadena. Los
triggers de la migración 0003 exigen todo eso al confirmar (RN-F-01, RN-F-07).
Lo que no haría ``IssueInvoice`` es el contenido: al 10 % con toda la base en
material, algo que hoy el dominio no deja emitir (RN-F-13).
"""

import asyncio
import dataclasses
from datetime import date
from uuid import uuid4

import pytest

from kapataz.domain.billing.errors import InvalidInvoiceError, IssuedAmountsMismatchError
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import Series
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.billing_support import (
    ISSUER_ADDRESS,
    ISSUER_TAX_ID,
    RECIPIENT_ADDRESS,
    RECIPIENT_TAX_ID,
    SYSTEM,
    add_customer,
    add_draft,
    create_account,
)
from tests.integration.conftest import APP_ROLE
from tests.integration.persistence.conftest import ISSUE_AT
from tests.integration.persistence.sql_support import run_transaction

# Base de ``two_lines``: 1.250 €. Al 10 %, 125 € de cuota y 1.375 € de total.
_BASE_CENTS = 125_000
_TAX_CENTS = 12_500
_ISSUE_DATE = date(2026, 11, 18)

_ALL_MATERIAL = "UPDATE invoice_lines SET is_material = true WHERE invoice_id = :id"

# La emisión crea la cabeza vacía y el contador a cero si no existen.
_NEW_HEAD = "INSERT INTO billing_chain_heads (tenant_id, last_record_id) VALUES (:t, NULL)"
_NEW_COUNTER = (
    "INSERT INTO series_counters (tenant_id, series, year, last_number, last_issue_date) "
    "VALUES (:t, :series, 2026, 0, NULL)"
)

_ISSUE_AT_10_WITH_ALL_MATERIAL = """
UPDATE invoices SET
    tax_rate = 10, recipient_type = 'private', dwelling_over_two_years = true,
    base_total = CAST(:base AS integer), tax_total = CAST(:tax AS integer),
    total_amount = CAST(:base AS integer) + CAST(:tax AS integer),
    amount_due = CAST(:base AS integer) + CAST(:tax AS integer),
    status = 'issued', issue_year = 2026, number = 1,
    issue_date = :issue_date, issued_at = :issued_at,
    issuer_name = 'Reformas Ejemplo', issuer_tax_id = :issuer_tax_id,
    issuer_address = :issuer_address,
    recipient_name = 'Cliente Ejemplo', recipient_tax_id = :recipient_tax_id,
    recipient_address = :recipient_address
WHERE id = :id
"""

_COUNTER_TO_ONE = (
    "UPDATE series_counters SET last_number = 1, last_issue_date = :issue_date "
    "WHERE tenant_id = :t AND series = :series AND year = 2026"
)

# Primer registro de la cadena. La base de datos no puede comprobar la huella
# (la calcula el dominio); esta prueba no lee la cadena, solo la factura.
_FIRST_RECORD = """
INSERT INTO billing_records (
    id, tenant_id, invoice_id, previous_record_id, record_type, is_correction,
    prior_rejection, issuer_tax_id, series_number, issue_date, is_first,
    system_name, system_id, system_version, installation_number, generated_at,
    canonical_json, hash, submission_status, sent_with_incident
) VALUES (
    :record, :t, :id, NULL, 'registration', false,
    false, :issuer_tax_id, :series_number, :issue_date, true,
    :system_name, :system_id, :system_version, :installation_number, :issued_at,
    '{}', repeat('A', 64), 'pending', false
)
"""

_HEAD_TO_RECORD = "UPDATE billing_chain_heads SET last_record_id = :record WHERE tenant_id = :t"


def _issued_by_sql(database, factory, *, tax_cents: int = _TAX_CENTS):
    """Cuenta con una factura emitida que hoy no pasaría la regla del 40 %."""
    tenant_id = asyncio.run(create_account(factory))
    customer_id = asyncio.run(add_customer(factory, tenant_id))
    invoice_id = asyncio.run(add_draft(factory, tenant_id, customer_id))
    series = Series.invoices()
    params = {
        "t": tenant_id,
        "id": invoice_id,
        "record": uuid4(),
        "series": series.code,
        "series_number": f"{series.code}-2026-0001",
        "base": _BASE_CENTS,
        "tax": tax_cents,
        "issue_date": _ISSUE_DATE,
        "issued_at": ISSUE_AT,
        "issuer_tax_id": str(ISSUER_TAX_ID),
        "issuer_address": ISSUER_ADDRESS,
        "recipient_tax_id": str(RECIPIENT_TAX_ID),
        "recipient_address": RECIPIENT_ADDRESS,
        "system_name": SYSTEM.system_name,
        "system_id": SYSTEM.system_id,
        "system_version": SYSTEM.version,
        "installation_number": SYSTEM.installation_number,
    }
    # En el orden de IssueInvoice: borrador, cabeza, contador, factura, contador,
    # registro y cabeza. Los triggers diferidos lo comprueban al confirmar.
    run_transaction(
        database,
        APP_ROLE,
        [
            (_ALL_MATERIAL, params),
            (_NEW_HEAD, params),
            (_NEW_COUNTER, params),
            (_ISSUE_AT_10_WITH_ALL_MATERIAL, params),
            (_COUNTER_TO_ONE, params),
            (_FIRST_RECORD, params),
            (_HEAD_TO_RECORD, params),
        ],
        tenant_id=tenant_id,
    )
    return tenant_id, invoice_id


def _read(factory, tenant_id, invoice_id, *, for_update: bool):
    async def read():
        async with factory() as uow:
            await uow.set_tenant(tenant_id)
            if for_update:
                return await uow.invoices.get_for_update(invoice_id)
            return await uow.invoices.get(invoice_id)

    return asyncio.run(read())


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize("for_update", [False, True], ids=["get", "get_for_update"])
def test_una_emitida_que_hoy_incumple_una_regla_de_emision_se_sigue_leyendo(
    database, app_factory, for_update
):
    tenant_id, invoice_id = _issued_by_sql(database, app_factory)

    invoice = _read(app_factory, tenant_id, invoice_id, for_update=for_update)

    assert invoice is not None
    assert invoice.is_issued
    assert str(invoice.number) == "F-2026-0001"
    assert invoice.treatment == VatTreatment.taxed(TaxRate.reduced())
    assert all(line.is_material for line in invoice.lines)
    assert invoice.totals.tax == Money.of("125.00")
    # Con las reglas vigentes no se podría crear: el 40 % de material la manda al 21 %.
    with pytest.raises(InvalidInvoiceError, match="40 %"):
        dataclasses.replace(invoice)


@pytest.mark.req("RN-F-02")
def test_una_emitida_con_importes_alterados_fuera_de_la_app_no_se_lee(database, app_factory):
    # Un céntimo de más en la cuota, con el total y el importe a cobrar
    # cuadrados para que la restricción de la tabla no lo detecte.
    tenant_id, invoice_id = _issued_by_sql(database, app_factory, tax_cents=_TAX_CENTS + 1)

    with pytest.raises(IssuedAmountsMismatchError, match="tax, total_amount, amount_due"):
        _read(app_factory, tenant_id, invoice_id, for_update=False)
