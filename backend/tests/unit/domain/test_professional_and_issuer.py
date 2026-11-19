"""Profesional como emisor, datos que faltan para emitir y bloque SistemaInformatico."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.billing_record import SystemInfo
from kapataz.domain.billing.errors import InvalidBillingRecordError, MissingIssueDataError
from kapataz.domain.billing.party import (
    Party,
    missing_issuer_data,
    missing_recipient_data,
)
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.customers.tax_id import TaxId
from kapataz.domain.settings.professional import InvalidProfessionalError, Professional
from tests.unit.domain.billing_factories import SYSTEM

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
TENANT = TenantId(uuid4())


def professional(**overrides) -> Professional:
    values = {
        "tenant_id": TENANT,
        "name": "Reformas Ejemplo",
        "tax_id": TaxId("12345678Z"),
        "address": "Calle Mayor 1, 28001 Madrid",
        "updated_at": NOW,
    }
    values.update(overrides)
    return Professional(**values)


@pytest.mark.req("RN-F-06")
def test_el_profesional_completo_es_el_emisor():
    assert Party.issuer_from(professional()) == Party(
        "Reformas Ejemplo", TaxId("12345678Z"), "Calle Mayor 1, 28001 Madrid"
    )
    assert missing_issuer_data(professional()) == ()


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize(
    ("overrides", "missing"),
    [
        ({"tax_id": None}, ("issuer_tax_id",)),
        ({"address": None}, ("issuer_address",)),
        ({"tax_id": None, "address": None}, ("issuer_tax_id", "issuer_address")),
    ],
)
def test_sin_nif_o_domicilio_el_profesional_no_emite(overrides, missing):
    with pytest.raises(MissingIssueDataError) as error:
        Party.issuer_from(professional(**overrides))
    assert error.value.missing == missing


@pytest.mark.req("RN-F-06")
def test_sin_datos_del_profesional_faltan_todos():
    assert missing_issuer_data(None) == ("issuer_name", "issuer_tax_id", "issuer_address")
    with pytest.raises(MissingIssueDataError):
        Party.issuer_from(None)


@pytest.mark.req("RN-F-06")
def test_datos_del_destinatario_que_faltan():
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=TENANT,
        name="Cliente",
        tax_id=None,
        address=None,
        created_at=NOW,
    )
    assert missing_recipient_data(customer) == ("recipient_tax_id", "recipient_address")


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": " Reformas"},
        {"name": "x" * 121},
        {"address": ""},
        {"address": "x" * 251},
        {"updated_at": datetime(2026, 11, 18, 9, 0)},  # noqa: DTZ001 - sin zona a propósito
    ],
)
def test_datos_del_profesional_no_validos(overrides):
    with pytest.raises(InvalidProfessionalError):
        professional(**overrides)


@pytest.mark.req("RN-F-07")
def test_el_bloque_del_sistema_se_reconstruye_de_su_contenido_canonico():
    assert SystemInfo.from_canonical(SYSTEM.canonical()) == SYSTEM


@pytest.mark.req("RN-F-07")
@pytest.mark.parametrize(
    "block",
    [
        None,
        "texto",
        {**SYSTEM.canonical(), "TipoUsoPosibleSoloVerifactu": "X"},
        {k: v for k, v in SYSTEM.canonical().items() if k != "Version"},
    ],
)
def test_un_bloque_del_sistema_mal_formado_se_rechaza(block):
    with pytest.raises(InvalidBillingRecordError):
        SystemInfo.from_canonical(block)
