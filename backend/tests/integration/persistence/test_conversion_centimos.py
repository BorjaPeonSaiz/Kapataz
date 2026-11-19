"""Ida y vuelta entre Money y céntimos INTEGER en PostgreSQL real (ADR-009, «Verificación»)."""

import asyncio
from uuid import uuid4

import pytest

from kapataz.domain.billing.money import Money
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId, CatalogItemOrigin
from tests.billing_support import SEED_AT, create_account
from tests.integration.conftest import OWNER_ROLE
from tests.integration.persistence.conftest import run_sql


@pytest.mark.req("RN-01")
@pytest.mark.parametrize(
    ("amount", "cents"),
    [("0.01", 1), ("45.90", 4590), ("1512.50", 151250), ("21474836.47", 2_147_483_647)],
)
def test_un_importe_se_guarda_en_centimos_y_vuelve_igual(app_factory, database, amount, cents):
    tenant_id = asyncio.run(create_account(app_factory))
    item = CatalogItem(
        id=CatalogItemId(uuid4()),
        tenant_id=tenant_id,
        concept="Concepto",
        unit="ud",
        reference_price=Money.of(amount),
        origin=CatalogItemOrigin.MANUAL,
        is_material=False,
        created_at=SEED_AT,
    )

    async def round_trip():
        async with app_factory() as uow:
            await uow.set_tenant(tenant_id)
            await uow.catalog.add(item)
            await uow.commit()
        async with app_factory() as uow:
            await uow.set_tenant(tenant_id)
            return await uow.catalog.get(item.id)

    loaded = asyncio.run(round_trip())

    assert loaded is not None
    assert loaded.reference_price == Money.of(amount)
    assert str(loaded.reference_price) == amount
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT reference_price, pg_typeof(reference_price)::text FROM catalog_items "
        "WHERE id = :id",
        {"id": item.id},
    )
    assert rows == [(cents, "integer")]
