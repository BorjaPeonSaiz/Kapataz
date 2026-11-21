"""Casos de uso de carga del espacio de demostración con la unidad de trabajo en memoria.

``LoadDemoSpace`` carga el espacio de la cuenta de la sesión, la del usuario
autenticado (S3-R-03); ``LoadDemoSpaceForAccountId`` y
``LoadDemoSpaceForAccount``, de administración, el de la cuenta de un id o de
un email (RF-CF-04, S3-09). Las tres comparten el núcleo
(``demo_space_loader``).

Las mismas reglas se repiten contra PostgreSQL, con el dataset sintético, en
``tests/integration/persistence/test_seed_demo.py``.
"""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from kapataz.application.ports.repositories import TenantMismatchError
from kapataz.application.use_cases.account_creation import add_account
from kapataz.application.use_cases.admin.load_demo_space_for_account import (
    LoadDemoSpaceForAccount,
)
from kapataz.application.use_cases.admin.load_demo_space_for_account_id import (
    LoadDemoSpaceForAccountId,
)
from kapataz.application.use_cases.demo_space import DemoContent
from kapataz.application.use_cases.load_demo_space import LoadDemoSpace
from kapataz.domain.accounts.email_address import EmailAddress
from kapataz.domain.accounts.errors import (
    AccountNotFoundError,
    DemoSpaceAlreadyExistsError,
    InvalidDemoParentError,
    InvalidEmailError,
)
from kapataz.domain.accounts.model import (
    AuthenticatedUser,
    SessionId,
    TenantId,
    TenantKind,
    demo_tenant_id,
)
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.ids import QuoteId, QuoteLineId, QuoteVersionId
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.quantity import Quantity
from kapataz.domain.billing.quote import PriceSource, Quote, QuoteLine, QuoteStatus, QuoteVersion
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from kapataz.domain.customers.errors import DuplicateCustomerTaxIdError
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.settings.professional import Professional
from kapataz.infrastructure.clock import FrozenClock
from tests.billing_support import ISSUER_TAX_ID, RECIPIENT_TAX_ID
from tests.fakes.memory_uow import MemoryAccounts, MemoryUnitOfWorkFactory

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
SINCE = datetime(2025, 1, 2, 9, 0, tzinfo=UTC)
EMAIL = "demo@example.com"


def _customer(tenant_id: TenantId) -> Customer:
    return Customer(
        id=CustomerId(uuid4()),
        tenant_id=tenant_id,
        name="Cliente Demo",
        tax_id=RECIPIENT_TAX_ID,
        address="Calle Falsa 1, 39001 Santander",
        created_at=SINCE,
    )


def _content(tenant_id: TenantId, *, twin_customers: bool = False) -> DemoContent:
    customer = _customer(tenant_id)
    customers = (customer, _customer(tenant_id)) if twin_customers else (customer,)
    item = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept="Punto de luz",
        unit="ud",
        reference_price=Money.of("45.00"),
        origin=CatalogItemOrigin.MANUAL,
        is_material=False,
        created_at=SINCE,
    )
    line = QuoteLine(
        id=QuoteLineId(uuid4()),
        description="Punto de luz",
        quantity=Quantity(Decimal(3)),
        unit_price=Money.of("45.00"),
        price_source=PriceSource.manual(),
    )
    quote = Quote(
        id=QuoteId(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer.id,
        number=DocumentNumber(Series.quotes(), 2025, 1),
        status=QuoteStatus.SENT,
        versions=(
            QuoteVersion(
                id=QuoteVersionId(uuid4()),
                version=1,
                lines=(line,),
                recipient_type=RecipientType.PRIVATE,
                dwelling_over_two_years=True,
                valid_until=date(2025, 2, 1),
                created_at=SINCE,
            ),
        ),
        created_at=SINCE,
    )
    return DemoContent(
        professional=Professional(
            tenant_id=tenant_id,
            name="Electricidad Demo",
            tax_id=ISSUER_TAX_ID,
            address="Calle Mayor 1, 39001 Santander",
            updated_at=SINCE,
        ),
        customers=customers,
        catalog=(item,),
        quotes=(quote,),
    )


class Scenario:
    def __init__(self) -> None:
        self.factory = MemoryUnitOfWorkFactory()
        self.use_case = LoadDemoSpace(self.factory, FrozenClock(NOW))
        self.for_account_id = LoadDemoSpaceForAccountId(self.factory, FrozenClock(NOW))
        self.for_account = LoadDemoSpaceForAccount(self.factory, FrozenClock(NOW))
        self.user = asyncio.run(self._account(EMAIL))
        self.parent = self.user.tenant_id

    async def _account(self, email: str) -> AuthenticatedUser:
        """Alta de una cuenta y el usuario de su sesión, como lo deja AuthenticateSession."""
        async with self.factory() as uow:
            user_id = await add_account(
                uow, EmailAddress.parse(email), "hash", now=NOW, verified=True
            )
            await uow.commit()
        user = self.factory.state.users[user_id]
        return AuthenticatedUser(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            session_id=SessionId(uuid4()),
        )

    def other_account(self, email: str) -> AuthenticatedUser:
        return asyncio.run(self._account(email))


@pytest.mark.req("RF-CF-04")
def test_desde_el_email_crea_el_espacio_con_su_padre_y_carga_el_contenido():
    s = Scenario()
    built: list[TenantId] = []

    def build(tenant_id: TenantId) -> DemoContent:
        built.append(tenant_id)
        return _content(tenant_id)

    loaded = asyncio.run(s.for_account.execute(EMAIL.upper(), build))

    demo_id = demo_tenant_id(s.parent)
    assert built == [demo_id]
    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (s.parent, demo_id)
    assert (loaded.customers, loaded.catalog_items, loaded.quotes) == (1, 1, 1)
    state = s.factory.state
    demo = state.tenants[demo_id]
    assert (demo.kind, demo.parent_tenant_id, demo.name, demo.created_at) == (
        TenantKind.DEMO,
        s.parent,
        None,
        NOW,
    )
    assert state.professionals[demo_id].name == "Electricidad Demo"
    assert s.parent not in state.professionals
    rows = (*state.customers.values(), *state.catalog.values(), *state.quotes.values())
    assert {row.tenant_id for row in rows} == {demo_id}


@pytest.mark.req("RF-CF-04")
def test_desde_la_cuenta_de_la_sesion_hace_lo_mismo():
    s = Scenario()
    loaded = asyncio.run(s.use_case.execute(s.user, _content))
    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (s.parent, demo_tenant_id(s.parent))
    assert s.factory.state.tenants[loaded.demo_tenant_id].parent_tenant_id == s.parent


@pytest.mark.req("RF-CF-04")
def test_desde_el_id_de_la_cuenta_hace_lo_mismo():
    s = Scenario()
    loaded = asyncio.run(s.for_account_id.execute(s.parent, _content))
    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (s.parent, demo_tenant_id(s.parent))
    assert s.factory.state.tenants[loaded.demo_tenant_id].parent_tenant_id == s.parent


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_desde_la_sesion_el_espacio_es_siempre_el_de_la_cuenta_del_usuario():
    """S3-R-03: la cuenta sale del usuario autenticado; la otra no se toca."""
    s = Scenario()
    other = s.other_account("otra@example.com")
    loaded = asyncio.run(s.use_case.execute(other, _content))
    assert (loaded.parent_tenant_id, loaded.demo_tenant_id) == (
        other.tenant_id,
        demo_tenant_id(other.tenant_id),
    )
    assert demo_tenant_id(s.parent) not in s.factory.state.tenants


@pytest.mark.req("RF-CF-04")
def test_una_segunda_carga_falla_sin_escribir_nada():
    s = Scenario()
    asyncio.run(s.use_case.execute(s.user, _content))
    before = s.factory.state.copy()

    with pytest.raises(DemoSpaceAlreadyExistsError, match="ya tiene un espacio"):
        asyncio.run(s.for_account.execute(EMAIL, _content))
    with pytest.raises(DemoSpaceAlreadyExistsError, match="ya tiene un espacio"):
        asyncio.run(s.for_account_id.execute(s.parent, _content))
    with pytest.raises(DemoSpaceAlreadyExistsError, match="ya tiene un espacio"):
        asyncio.run(s.use_case.execute(s.user, _content))

    assert s.factory.state == before


@pytest.mark.req("RF-CF-04")
def test_dos_cargas_a_la_vez_la_segunda_falla_con_el_mismo_error(monkeypatch):
    """La clave primaria del id derivado decide si las dos ven el espacio libre."""
    s = Scenario()
    asyncio.run(s.use_case.execute(s.user, _content))
    before = s.factory.state.copy()

    # La carga que pierde la carrera vio la cuenta, pero aún no el espacio de la otra.
    real = {s.parent: s.factory.state.tenants[s.parent]}

    async def sees_parent_only(self, tenant_id):
        return real.get(tenant_id)

    monkeypatch.setattr(MemoryAccounts, "get_tenant", sees_parent_only)
    with pytest.raises(DemoSpaceAlreadyExistsError):
        asyncio.run(s.use_case.execute(s.user, _content))
    assert s.factory.state == before


@pytest.mark.req("RF-CF-04")
def test_cuenta_inexistente_o_email_no_valido():
    s = Scenario()
    before = s.factory.state.copy()
    with pytest.raises(AccountNotFoundError, match="ninguna cuenta con ese email"):
        asyncio.run(s.for_account.execute("nadie@example.com", _content))
    with pytest.raises(AccountNotFoundError):
        asyncio.run(s.for_account_id.execute(TenantId(uuid4()), _content))
    with pytest.raises(InvalidEmailError):
        asyncio.run(s.for_account.execute("no-es-un-email", _content))
    assert s.factory.state == before


@pytest.mark.req("RF-CF-04")
def test_un_espacio_de_demostracion_no_tiene_espacio_propio():
    s = Scenario()
    loaded = asyncio.run(s.use_case.execute(s.user, _content))
    with pytest.raises(InvalidDemoParentError):
        asyncio.run(s.for_account_id.execute(loaded.demo_tenant_id, _content))


@pytest.mark.req("RF-CF-04")
def test_si_algo_falla_a_mitad_no_queda_nada_ni_el_espacio():
    s = Scenario()
    before = s.factory.state.copy()
    with pytest.raises(DuplicateCustomerTaxIdError):
        asyncio.run(s.use_case.execute(s.user, lambda t: _content(t, twin_customers=True)))
    assert s.factory.state == before


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_un_contenido_de_otra_cuenta_no_se_escribe():
    s = Scenario()
    other = s.other_account("otra@example.com").tenant_id
    before = s.factory.state.copy()
    for target in (s.parent, other):
        with pytest.raises(TenantMismatchError):
            asyncio.run(s.use_case.execute(s.user, lambda _t, target=target: _content(target)))
    assert s.factory.state == before
