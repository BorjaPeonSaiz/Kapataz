"""TaxId (NIF, NIE y CIF), Customer, Party y CatalogItem."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.domain.billing.errors import InvalidInvoiceError, MissingIssueDataError
from kapataz.domain.billing.party import Party
from kapataz.domain.catalog.model import (
    CatalogItem,
    CatalogItemId,
    CatalogItemOrigin,
    InvalidCatalogItemError,
)
from kapataz.domain.customers.errors import InvalidCustomerError, InvalidTaxIdError
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.customers.tax_id import TaxId, TaxIdKind
from tests.unit.domain.billing_factories import money

NOW = datetime(2026, 11, 18, tzinfo=UTC)


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("12345678Z", TaxIdKind.DNI),
        ("00000000T", TaxIdKind.DNI),
        ("K1234567L", TaxIdKind.DNI),
        ("X1234567L", TaxIdKind.NIE),
        ("Y1234567X", TaxIdKind.NIE),
        ("Z1234567R", TaxIdKind.NIE),
        ("B12345674", TaxIdKind.CIF),
        ("A58818501", TaxIdKind.CIF),
        ("Q2826000H", TaxIdKind.CIF),
        ("N0012345E", TaxIdKind.CIF),
        ("G12345674", TaxIdKind.CIF),
        ("G1234567D", TaxIdKind.CIF),
    ],
)
def test_nif_validos(value, kind):
    tax_id = TaxId(value)
    assert tax_id.kind is kind
    assert str(tax_id) == value


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize(
    "value",
    [
        "12345678A",  # letra de control incorrecta
        "X1234567A",
        "B12345675",  # dígito de control incorrecto
        "A5881850A",  # una sociedad anónima lleva cifra, no letra
        "Q28260008",  # un organismo público lleva letra, no cifra
        "N00123455",  # un no residente lleva letra
        "I12345674",  # letra de entidad que no existe
        "1234567Z",  # ocho caracteres
        "123456789Z",  # diez
        "12345678z",  # sin normalizar
        "１2345678Z",  # cifra no ASCII
        "",
    ],
)
def test_nif_no_validos(value):
    with pytest.raises(InvalidTaxIdError):
        TaxId(value)


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("raw", ["12345678-z", " 12.345.678 Z ", "12345678z"])
def test_nif_se_normaliza(raw):
    assert TaxId.parse(raw) == TaxId("12345678Z")


@pytest.mark.req("RF-IN-08")
def test_cliente_sin_nif_se_puede_guardar():
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=TenantId(uuid4()),
        name="Marta López",
        tax_id=None,
        address=None,
        created_at=NOW,
    )
    assert customer.tax_id is None


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("name", ["", "  ", " Marta", "x" * 121])
def test_cliente_con_nombre_no_valido(name):
    with pytest.raises(InvalidCustomerError):
        Customer(
            id=CustomerId(uuid4()),
            tenant_id=TenantId(uuid4()),
            name=name,
            tax_id=None,
            address=None,
            created_at=NOW,
        )


@pytest.mark.req("RN-F-06")
def test_cliente_con_fecha_sin_zona():
    with pytest.raises(InvalidCustomerError):
        Customer(
            id=CustomerId(uuid4()),
            tenant_id=TenantId(uuid4()),
            name="Marta",
            tax_id=None,
            address=None,
            created_at=datetime(2026, 1, 1),  # noqa: DTZ001
        )


@pytest.mark.req("RN-F-06")
def test_destinatario_exige_nif():
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=TenantId(uuid4()),
        name="Marta López",
        tax_id=None,
        address=None,
        created_at=NOW,
    )
    with pytest.raises(MissingIssueDataError) as error:
        Party.recipient_from(customer)
    assert error.value.missing == ("recipient_tax_id", "recipient_address")


@pytest.mark.req("RN-F-06")
def test_destinatario_exige_domicilio():
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=TenantId(uuid4()),
        name="Marta López",
        tax_id=TaxId("12345678Z"),
        address=None,
        created_at=NOW,
    )
    with pytest.raises(MissingIssueDataError) as error:
        Party.recipient_from(customer)
    assert error.value.missing == ("recipient_address",)


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("address", ["", "  ", " Calle Mayor 1", "Calle Mayor 1 ", "x" * 251])
def test_domicilio_no_valido(address):
    with pytest.raises(InvalidCustomerError):
        Customer(
            id=CustomerId(uuid4()),
            tenant_id=TenantId(uuid4()),
            name="Marta",
            tax_id=None,
            address=address,
            created_at=NOW,
        )
    with pytest.raises(InvalidInvoiceError):
        Party("Marta", TaxId("12345678Z"), address)


@pytest.mark.req("RN-F-06")
def test_domicilio_de_250_caracteres():
    assert Party("Marta", TaxId("12345678Z"), "x" * 250).address == "x" * 250


@pytest.mark.req("RN-F-06")
def test_destinatario_desde_cliente_con_nif():
    customer = Customer(
        id=CustomerId(uuid4()),
        tenant_id=TenantId(uuid4()),
        name="Marta López",
        tax_id=TaxId("12345678Z"),
        address="Calle Mayor 1",
        created_at=NOW,
    )
    assert Party.recipient_from(customer) == Party(
        "Marta López", TaxId("12345678Z"), "Calle Mayor 1"
    )


@pytest.mark.req("RN-F-06")
@pytest.mark.parametrize("name", ["", " Ana", "x" * 121])
def test_parte_con_nombre_no_valido(name):
    with pytest.raises(InvalidInvoiceError):
        Party(name, TaxId("12345678Z"), "Calle Mayor 1")


@pytest.mark.req("RF-CF-02")
def test_concepto_del_catalogo():
    item = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=TenantId(uuid4()),
        concept="Punto de luz",
        unit="ud",
        reference_price=money("45.00"),
        origin=CatalogItemOrigin.HISTORY,
        is_material=False,
        created_at=NOW,
    )
    assert item.reference_price == money("45.00")


@pytest.mark.req("RF-CF-02")
@pytest.mark.parametrize(
    ("concept", "unit", "price", "created_at"),
    [
        ("", "ud", None, NOW),
        ("Punto de luz", "", None, NOW),
        ("Punto de luz", "ud", "0.00", NOW),
        ("Punto de luz", "ud", None, datetime(2026, 1, 1)),  # noqa: DTZ001
    ],
)
def test_concepto_no_valido(concept, unit, price, created_at):
    with pytest.raises(InvalidCatalogItemError):
        CatalogItem(
            id=CatalogItemId(uuid4()),
            tenant_id=TenantId(uuid4()),
            concept=concept,
            unit=unit,
            reference_price=None if price is None else money(price),
            origin=CatalogItemOrigin.MANUAL,
            is_material=False,
            created_at=created_at,
        )


@pytest.mark.req("RN-F-06")
def test_parte_con_nombre_de_120_caracteres():
    assert Party("x" * 120, TaxId("12345678Z"), "Calle Mayor 1").name == "x" * 120
