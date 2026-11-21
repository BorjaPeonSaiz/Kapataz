"""``tenants`` endurecida para el espacio de demostración (migración 0004, S3-01, I-5).

SQL directo contra PostgreSQL, sin pasar por el dominio: lo que se prueba es
que la base de datos se defiende sola. Con ``kapataz_app`` (sin BYPASSRLS),
salvo donde se dice: el propietario no queda filtrado por RLS y los triggers
actúan también para él.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.integration.persistence.conftest import run_sql
from tests.integration.persistence.sql_support import attempt, run_transaction

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
HIERARCHY = "KZF14"
INSUFFICIENT_PRIVILEGE = "42501"
UNIQUE_VIOLATION = "23505"

_INSERT_STANDARD = (
    "INSERT INTO public.tenants (id, name, kind, created_at) VALUES (:id, NULL, 'standard', :now)"
)
_INSERT_DEMO = (
    "INSERT INTO public.tenants (id, name, kind, parent_tenant_id, created_at) "
    "VALUES (:id, NULL, 'demo', :parent, :now)"
)


def _standard(database) -> UUID:
    """Cuenta normal, dada de alta por la app con ella misma fijada."""
    tenant_id = uuid4()
    run_transaction(
        database, APP_ROLE, [(_INSERT_STANDARD, {"id": tenant_id, "now": NOW})], tenant_id=tenant_id
    )
    return tenant_id


def _demo_of(database, parent: UUID) -> UUID:
    """El espacio de ``parent``, dado de alta por la app con ``parent`` fijada."""
    demo = uuid4()
    run_transaction(
        database,
        APP_ROLE,
        [(_INSERT_DEMO, {"id": demo, "parent": parent, "now": NOW})],
        tenant_id=parent,
    )
    return demo


def _insert_demo(parent: UUID, demo: UUID | None = None):
    return [(_INSERT_DEMO, {"id": demo or uuid4(), "parent": parent, "now": NOW})]


@pytest.mark.req("RF-CF-04")
def test_la_app_da_de_alta_el_espacio_de_la_cuenta_fijada(database):
    parent = _standard(database)
    demo = _demo_of(database, parent)
    rows = run_sql(
        database,
        OWNER_ROLE,
        "SELECT kind, parent_tenant_id FROM public.tenants WHERE id = :id",
        {"id": demo},
    )
    assert [tuple(row) for row in rows] == [("demo", parent)]


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_un_padre_ajeno_y_uno_inexistente_dan_el_mismo_error(database):
    mine, other = _standard(database), _standard(database)
    missing = uuid4()
    own_demo = uuid4()

    # Con la cuenta propia fijada (política demo_space_from_parent) y con el
    # propio espacio fijado (política tenant_isolation): la otra cuenta no se
    # ve, así que el error es el mismo que si no existiera.
    rejections = [
        attempt(database, APP_ROLE, _insert_demo(parent, demo), tenant_id=fixed)
        for fixed, demo in ((mine, None), (own_demo, own_demo))
        for parent in (other, missing)
    ]

    assert all(r is not None and r.sqlstate == HIERARCHY for r in rejections), rejections
    assert len({r.message for r in rejections if r is not None}) == 1
    assert run_sql(
        database,
        OWNER_ROLE,
        "SELECT count(*) FROM public.tenants WHERE parent_tenant_id IN (:a, :b)",
        {"a": other, "b": missing},
    ) == [(0,)]


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("role", [APP_ROLE, OWNER_ROLE])
def test_un_espacio_de_demostracion_no_tiene_otro_dentro(database, role):
    demo = _demo_of(database, _standard(database))

    rejection = attempt(database, role, _insert_demo(demo), tenant_id=demo)

    assert rejection is not None
    assert (rejection.sqlstate, "no tiene otro dentro" in rejection.message) == (HIERARCHY, True)


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize("role", [APP_ROLE, OWNER_ROLE])
def test_una_cuenta_no_tiene_dos_espacios_aunque_lleven_otro_id(database, role):
    parent = _standard(database)
    _demo_of(database, parent)

    rejection = attempt(database, role, _insert_demo(parent), tenant_id=parent)

    assert rejection is not None
    assert rejection.sqlstate == UNIQUE_VIOLATION, rejection
    assert "uq_tenants_parent_tenant_id" in rejection.message


@pytest.mark.req("RF-CF-04")
@pytest.mark.parametrize(
    "assignment",
    [
        "kind = 'standard', parent_tenant_id = NULL",
        "parent_tenant_id = :other",
        "id = :new_id",
    ],
)
def test_ni_el_tipo_ni_el_padre_ni_el_id_cambian_ni_para_el_propietario(database, assignment):
    parent, other = _standard(database), _standard(database)
    demo = _demo_of(database, parent)
    params = {"demo": demo, "other": other, "new_id": uuid4()}

    rejection = attempt(
        database,
        OWNER_ROLE,
        [(f"UPDATE public.tenants SET {assignment} WHERE id = :demo", params)],
    )

    assert rejection is not None
    assert rejection.sqlstate == HIERARCHY, rejection


@pytest.mark.req("RF-CF-04")
@pytest.mark.req("RNF-13")
@pytest.mark.parametrize(
    "assignment",
    [
        "kind = 'standard', parent_tenant_id = NULL",
        "parent_tenant_id = :other",
        "id = :new_id",
        "created_at = :now",
    ],
)
def test_la_app_solo_actualiza_el_nombre(database, assignment):
    parent, other = _standard(database), _standard(database)
    demo = _demo_of(database, parent)
    params = {"demo": demo, "other": other, "new_id": uuid4(), "now": NOW}

    renamed = attempt(
        database,
        APP_ROLE,
        [("UPDATE public.tenants SET name = 'Demo' WHERE id = :demo", params)],
        tenant_id=demo,
    )
    rejection = attempt(
        database,
        APP_ROLE,
        [(f"UPDATE public.tenants SET {assignment} WHERE id = :demo", params)],
        tenant_id=demo,
    )

    assert renamed is None
    assert rejection is not None
    assert rejection.sqlstate == INSUFFICIENT_PRIVILEGE, rejection


@pytest.mark.req("RNF-13")
def test_permisos_de_la_app_sobre_tenants(database):
    [row] = run_sql(
        database,
        OWNER_ROLE,
        "SELECT has_table_privilege(:app, 'public.tenants', 'UPDATE'), "
        "has_any_column_privilege(:app, 'public.tenants', 'UPDATE'), "
        "has_column_privilege(:app, 'public.tenants', 'name', 'UPDATE'), "
        "has_column_privilege(:app, 'public.tenants', 'kind', 'UPDATE'), "
        "has_column_privilege(:app, 'public.tenants', 'parent_tenant_id', 'UPDATE'), "
        "has_table_privilege(:app, 'public.tenants', 'DELETE')",
        {"app": APP_ROLE},
    )
    # Sin UPDATE de tabla: solo el de la columna name (basta para SELECT … FOR UPDATE).
    assert tuple(row) == (False, True, True, False, False, False)


@pytest.mark.req("RF-CF-04")
@pytest.mark.owasp("A08")
def test_una_tabla_temporal_no_hace_pasar_un_espacio_por_cuenta_normal(database):
    """Como en S2-01: el trigger nombra ``public.tenants`` y fija ``search_path``."""
    demo = _demo_of(database, _standard(database))

    rejection = attempt(
        database,
        OWNER_ROLE,
        [
            ("CREATE TEMP TABLE tenants (id uuid, kind text)", {}),
            ("INSERT INTO pg_temp.tenants VALUES (:demo, 'standard')", {"demo": demo}),
            *_insert_demo(demo),
        ],
    )

    assert rejection is not None
    assert rejection.sqlstate == HIERARCHY, rejection
