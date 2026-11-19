"""Destinatario y vivienda de la obra en la base de datos (RN-F-13, CHECK works_recipient).

Un borrador que sale de un presupuesto no lleva destinatario ni vivienda
propios: los toma de la versión del presupuesto y los copia al emitir. Una
emitida los lleva siempre (la vivienda solo falta si el destinatario es
empresa). Por SQL directo, con el rol de la app, la base de datos lo impide
aunque el código no lo haga.
"""

import asyncio
from datetime import date

import pytest

from kapataz.domain.billing.codes import RecipientType
from tests.billing_support import add_accepted_quote, add_customer, add_draft, create_account
from tests.integration.conftest import APP_ROLE
from tests.integration.persistence.conftest import ISSUE_AT
from tests.integration.persistence.sql_support import attempt

CONSTRAINT = "ck_invoices_works_recipient"

# Los demás datos de emitida, para que solo pueda fallar este CHECK.
_ISSUED_FIELDS = (
    "status = 'issued', issue_year = 2026, number = 1, issue_date = :d, issued_at = :at, "
    "issuer_name = 'Reformas Ejemplo', issuer_tax_id = '12345678Z', "
    "issuer_address = 'Calle Mayor 1', recipient_name = 'Cliente Ejemplo', "
    "recipient_tax_id = 'B12345674', recipient_address = 'Avenida del Puerto 2'"
)


def _expect_check(rejection):
    assert rejection is not None, "La base de datos lo aceptó."
    assert rejection.sqlstate == "23514", rejection  # check_violation
    assert CONSTRAINT in rejection.message, rejection


def _account_with_draft(factory):
    tenant_id = asyncio.run(create_account(factory))
    customer_id = asyncio.run(add_customer(factory, tenant_id))
    return tenant_id, customer_id, asyncio.run(add_draft(factory, tenant_id, customer_id))


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    "recipient",
    [
        "recipient_type = NULL, dwelling_over_two_years = NULL",
        "recipient_type = 'private', dwelling_over_two_years = NULL",
        "recipient_type = 'community', dwelling_over_two_years = NULL",
    ],
    ids=["sin-destinatario", "particular-sin-vivienda", "comunidad-sin-vivienda"],
)
def test_una_emitida_lleva_destinatario_y_vivienda(app_factory, database, recipient):
    tenant_id, _, draft_id = _account_with_draft(app_factory)
    params = {"id": draft_id, "d": date(2026, 11, 18), "at": ISSUE_AT}

    rejection = attempt(
        database,
        APP_ROLE,
        [(f"UPDATE invoices SET {_ISSUED_FIELDS}, {recipient} WHERE id = :id", params)],
        tenant_id=tenant_id,
    )

    _expect_check(rejection)


@pytest.mark.req("RN-F-13")
@pytest.mark.parametrize(
    "recipient",
    [
        "recipient_type = 'business', dwelling_over_two_years = NULL",
        "recipient_type = NULL, dwelling_over_two_years = true",
    ],
    ids=["con-destinatario", "con-vivienda"],
)
def test_un_borrador_con_presupuesto_no_lleva_destinatario_propio(app_factory, database, recipient):
    tenant_id, customer_id, draft_id = _account_with_draft(app_factory)
    version = asyncio.run(
        add_accepted_quote(
            app_factory,
            tenant_id,
            customer_id,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    )
    params = {"id": draft_id, "version": version.id}

    rejection = attempt(
        database,
        APP_ROLE,
        [
            (
                (f"UPDATE invoices SET quote_version_id = :version, {recipient} WHERE id = :id"),
                params,
            )
        ],
        tenant_id=tenant_id,
    )

    _expect_check(rejection)


@pytest.mark.req("RN-F-13")
def test_un_borrador_con_presupuesto_y_sin_destinatario_propio_vale(app_factory, database):
    # Control: el mismo cambio sin destinatario ni vivienda propios pasa.
    tenant_id, customer_id, draft_id = _account_with_draft(app_factory)
    version = asyncio.run(
        add_accepted_quote(
            app_factory,
            tenant_id,
            customer_id,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    )

    rejection = attempt(
        database,
        APP_ROLE,
        [
            (
                (
                    "UPDATE invoices SET quote_version_id = :version, recipient_type = NULL, "
                    "dwelling_over_two_years = NULL WHERE id = :id"
                ),
                {"id": draft_id, "version": version.id},
            )
        ],
        tenant_id=tenant_id,
    )

    assert rejection is None
