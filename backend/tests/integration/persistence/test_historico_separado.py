"""Las facturas emitidas, su serie y su cadena no tienen enlace con nada importado (ADR-017).

ADR-017 separa el histórico importado (``historical_invoices`` y
``historical_lines``, Bloque 4) de las facturas emitidas por la app. Esta
prueba fija, desde el catálogo de PostgreSQL, el lado del Bloque 2: el núcleo
fiscal (facturas, líneas, rectificaciones, contadores y cadena de registros)
solo apunta a la cuenta, a sus clientes y a sus presupuestos, y solo lo
apuntan sus propias tablas y los cobros. Si una tabla del histórico o de la
ingesta se enlaza con el núcleo, o el núcleo con ella, la prueba falla: eso es
la opción 2 que el ADR descarta, y necesita otro ADR.
"""

import pytest

from tests.integration.conftest import OWNER_ROLE
from tests.integration.persistence.conftest import run_sql

# Tablas donde viven la serie emitida (RN-F-01) y la cadena (RN-F-07).
FISCAL_CORE = frozenset(
    {
        "invoices",
        "invoice_lines",
        "invoice_corrections",
        "series_counters",
        "billing_chain_heads",
        "billing_records",
    }
)
# A qué puede apuntar el núcleo fiscal fuera de sí mismo. Los clientes son
# comunes al histórico y a las emitidas (RF-IN-08), pero son datos maestros:
# compartirlos no mete nada importado en la serie ni en la cadena.
CORE_MAY_POINT_TO = frozenset({"tenants", "customers", "quote_versions", "quote_lines"})
# Quién puede apuntar al núcleo fiscal desde fuera: los cobros de una factura emitida.
MAY_POINT_TO_CORE = frozenset({"payments"})


def _foreign_keys(database) -> list[tuple[str, str, str]]:
    return [
        (name, child, parent)
        for name, child, parent in run_sql(
            database,
            OWNER_ROLE,
            "SELECT con.conname, child.relname, parent.relname "
            "FROM pg_constraint con "
            "JOIN pg_class child ON child.oid = con.conrelid "
            "JOIN pg_class parent ON parent.oid = con.confrelid "
            "WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace",
        )
    ]


@pytest.mark.req("RN-F-08")
@pytest.mark.req("RF-IN-09")
def test_la_serie_y_la_cadena_no_se_enlazan_con_ninguna_tabla_ajena(database):
    keys = _foreign_keys(database)

    outgoing = [
        key
        for key in keys
        if key[1] in FISCAL_CORE and key[2] not in FISCAL_CORE | CORE_MAY_POINT_TO
    ]
    incoming = [
        key
        for key in keys
        if key[2] in FISCAL_CORE and key[1] not in FISCAL_CORE | MAY_POINT_TO_CORE
    ]

    assert outgoing == []
    assert incoming == []
    # El recorrido no puede salir vacío: las seis tablas existen y se enlazan.
    assert {child for _, child, parent in keys if parent in FISCAL_CORE} >= {
        "invoice_lines",
        "invoice_corrections",
        "billing_records",
        "billing_chain_heads",
        "payments",
    }
    assert {child for _, child, _ in keys} >= FISCAL_CORE


@pytest.mark.req("RN-F-08")
def test_un_registro_de_facturacion_solo_puede_citar_una_factura_de_invoices(database):
    keys = _foreign_keys(database)

    record_targets = {parent for _, child, parent in keys if child == "billing_records"}

    # La factura de un registro sale de ``invoices`` y de ningún otro sitio: un
    # documento importado no puede entrar en la cadena (ADR-017).
    assert record_targets == {"tenants", "invoices", "billing_records"}
