"""Lectura de facturas emitidas contra PostgreSQL real (RN-F-02).

Una factura emitida antes de que se endurezca una regla de emisión tiene que
seguir leyéndose. Para tener una así sin esperar a que cambie la normativa, la
prueba emite la fila por SQL: un borrador válido pasa a emitido al 10 % con
toda su base en material, algo que hoy el dominio no deja emitir (RN-F-13).
"""

import asyncio
import dataclasses
from datetime import date

import pytest

from kapataz.domain.billing.errors import InvalidInvoiceError, IssuedAmountsMismatchError
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from tests.billing_support import (
    ISSUER_ADDRESS,
    ISSUER_TAX_ID,
    RECIPIENT_ADDRESS,
    RECIPIENT_TAX_ID,
    add_customer,
    add_draft,
    create_account,
)
from tests.integration.conftest import APP_ROLE
from tests.integration.persistence.conftest import ISSUE_AT, run_sql

# Base de ``two_lines``: 1.250 €. Al 10 %, 125 € de cuota y 1.375 € de total.
_BASE_CENTS = 125_000
_TAX_CENTS = 12_500

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


def _issued_by_sql(database, factory, *, tax_cents: int = _TAX_CENTS):
    """Cuenta con una factura emitida que hoy no pasaría la regla del 40 %."""
    tenant_id = asyncio.run(create_account(factory))
    customer_id = asyncio.run(add_customer(factory, tenant_id))
    invoice_id = asyncio.run(add_draft(factory, tenant_id, customer_id))
    run_sql(
        database,
        APP_ROLE,
        "UPDATE invoice_lines SET is_material = true WHERE invoice_id = :id",
        {"id": invoice_id},
        tenant_id=tenant_id,
    )
    run_sql(
        database,
        APP_ROLE,
        _ISSUE_AT_10_WITH_ALL_MATERIAL,
        {
            "id": invoice_id,
            "base": _BASE_CENTS,
            "tax": tax_cents,
            "issue_date": date(2026, 11, 18),
            "issued_at": ISSUE_AT,
            "issuer_tax_id": str(ISSUER_TAX_ID),
            "issuer_address": ISSUER_ADDRESS,
            "recipient_tax_id": str(RECIPIENT_TAX_ID),
            "recipient_address": RECIPIENT_ADDRESS,
        },
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
