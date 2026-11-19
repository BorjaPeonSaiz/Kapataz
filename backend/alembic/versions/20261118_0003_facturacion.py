"""Facturación: profesional, clientes, catálogo, presupuestos, facturas, cadena y cobros.

Revision ID: 0003_facturacion
Revises: 0002_nombre_de_cuenta
Create Date: 2026-11-18

Tablas del Bloque 2 (plan §4.5, arquitectura §5.2):

- ``professional``, ``customers`` y ``catalog_items``;
- ``quotes``, ``quote_versions`` y ``quote_lines``;
- ``invoices``, ``invoice_lines`` e ``invoice_corrections``;
- ``series_counters``, ``billing_chain_heads``, ``billing_records`` y ``payments``.

Aislamiento (ADR-024, RNF-13):

- todas llevan ``tenant_id`` y la política ``tenant_isolation``, la misma que
  ``tenants``;
- las referencias entre ellas son claves foráneas compuestas ``(tenant_id, …)``
  contra un ``UNIQUE (tenant_id, id)``, así que la base de datos no deja
  enlazar filas de cuentas distintas.

Importes en céntimos ``INTEGER`` (ADR-009).

Permisos mínimos de ``kapataz_app``:

- sin ``DELETE`` en ``billing_records``, ``invoice_corrections`` ni
  ``series_counters``;
- ``DELETE`` en ``invoices`` e ``invoice_lines`` solo para borradores: lo
  impide el trigger con una factura emitida.

Triggers, que actúan también para el propietario (RN-F-02, RN-F-07):

- ``invoices``: con ``status = 'issued'``, ni ``UPDATE`` ni ``DELETE``.
- ``invoice_lines`` e ``invoice_corrections``: ni altas, ni cambios, ni
  bajas si su factura está emitida. Bloquean la fila de la factura con
  ``FOR SHARE``, así que no pueden cruzarse con una emisión en curso.
- ``billing_records``: sin ``DELETE`` y sin ``UPDATE`` salvo en las columnas
  de envío. Al insertar, el enlace (``prev_*``) tiene que copiar el registro
  anterior.
- ``billing_chain_heads``: nace vacía y solo avanza al registro que sigue al
  actual.
- ``TRUNCATE`` rechazado en las cuatro tablas fiscales, en los contadores, en la
  cabeza de la cadena y en los cobros: vaciarlas nunca es una operación normal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_facturacion"
down_revision: str | Sequence[str] | None = "0002_nombre_de_cuenta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "kapataz_app"
_CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Permisos de la app por tabla. UPDATE también lo exige SELECT … FOR UPDATE.
_GRANTS: dict[str, str] = {
    "professional": "SELECT, INSERT, UPDATE",
    "customers": "SELECT, INSERT, UPDATE",
    "catalog_items": "SELECT, INSERT, UPDATE",
    "quotes": "SELECT, INSERT, UPDATE",
    # Un presupuesto en borrador sustituye su versión actual (Quote.revise).
    "quote_versions": "SELECT, INSERT, UPDATE, DELETE",
    "quote_lines": "SELECT, INSERT, UPDATE, DELETE",
    # DELETE solo para borradores: el trigger lo impide con una emitida.
    "invoices": "SELECT, INSERT, UPDATE, DELETE",
    "invoice_lines": "SELECT, INSERT, UPDATE, DELETE",
    "invoice_corrections": "SELECT, INSERT",
    "series_counters": "SELECT, INSERT, UPDATE",
    "billing_chain_heads": "SELECT, INSERT, UPDATE",
    # UPDATE solo de las columnas de envío (Bloque 12): lo vigila el trigger.
    "billing_records": "SELECT, INSERT, UPDATE",
    "payments": "SELECT, INSERT",
}

_FISCAL_TABLES = ("invoices", "invoice_lines", "invoice_corrections", "billing_records")
# Tablas que no se vacían: las fiscales, la numeración, la cadena y los cobros.
_NO_TRUNCATE_TABLES = (*_FISCAL_TABLES, "series_counters", "billing_chain_heads", "payments")

# Columnas de billing_records que puede cambiar el resultado del envío.
_SUBMISSION_COLUMNS = (
    "submission_status",
    "error_code",
    "error_description",
    "submission_csv",
    "submitted_at",
    "sent_with_incident",
)

_FUNCTIONS = (
    "invoices_immutable_when_issued()",
    "invoice_children_immutable_when_issued()",
    "billing_records_append_only()",
    "billing_records_check_link()",
    "billing_chain_heads_advance()",
    "reject_truncate_of_fiscal_table()",
)

# RN-F-02. Hoy todas las columnas de una factura son fiscales, así que cualquier
# cambio de una emitida se rechaza. Si un día se añade una que no lo sea (la
# ruta del PDF, por ejemplo), se resta aquí del to_jsonb.
_INVOICES_IMMUTABLE = """
CREATE FUNCTION invoices_immutable_when_issued() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status = 'issued' THEN
            RAISE EXCEPTION 'RN-F-02: una factura emitida no se borra; se rectifica.'
                USING ERRCODE = 'KZF02';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'issued' AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
        RAISE EXCEPTION 'RN-F-02: una factura emitida no se modifica; se rectifica.'
            USING ERRCODE = 'KZF02';
    END IF;
    RETURN NEW;
END;
$$
"""

# TG_ARGV[0] es la columna que apunta a la factura. FOR SHARE espera a una
# emisión en curso (que bloquea la factura con FOR UPDATE) y, a la vez, impide
# que la factura se emita mientras esta transacción cambia sus líneas.
_CHILDREN_IMMUTABLE = """
CREATE FUNCTION invoice_children_immutable_when_issued() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    invoice_ids uuid[] := ARRAY[]::uuid[];
    parent_status text;
BEGIN
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        invoice_ids := invoice_ids || (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        invoice_ids := invoice_ids || (to_jsonb(OLD) ->> TG_ARGV[0])::uuid;
    END IF;
    FOR parent_status IN
        SELECT status FROM invoices WHERE id = ANY (invoice_ids) ORDER BY id FOR SHARE
    LOOP
        IF parent_status = 'issued' THEN
            RAISE EXCEPTION 'RN-F-02: % de una factura emitida no se modifica.', TG_TABLE_NAME
                USING ERRCODE = 'KZF02';
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
"""

_RECORDS_APPEND_ONLY = f"""
CREATE FUNCTION billing_records_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'RN-F-07: un registro de facturación no se borra.'
            USING ERRCODE = 'KZF07';
    END IF;
    IF to_jsonb(NEW) - ARRAY[{", ".join(f"'{c}'" for c in _SUBMISSION_COLUMNS)}]
        IS DISTINCT FROM
        to_jsonb(OLD) - ARRAY[{", ".join(f"'{c}'" for c in _SUBMISSION_COLUMNS)}] THEN
        RAISE EXCEPTION 'RN-F-07: de un registro solo cambia el resultado del envío.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NEW;
END;
$$
"""

# El enlace guardado tiene que ser copia exacta del registro anterior: así la
# cadena de la base de datos y la de las huellas son la misma.
_RECORDS_CHECK_LINK = """
CREATE FUNCTION billing_records_check_link() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    previous billing_records%ROWTYPE;
BEGIN
    IF NEW.previous_record_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO previous FROM billing_records
        WHERE tenant_id = NEW.tenant_id AND id = NEW.previous_record_id;
    IF NOT FOUND
        OR previous.hash IS DISTINCT FROM NEW.prev_hash
        OR previous.issuer_tax_id IS DISTINCT FROM NEW.prev_issuer_tax_id
        OR previous.series_number IS DISTINCT FROM NEW.prev_series_number
        OR previous.issue_date IS DISTINCT FROM NEW.prev_issue_date THEN
        RAISE EXCEPTION 'RN-F-07: el enlace no copia el registro anterior de la cadena.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NEW;
END;
$$
"""

_HEADS_ADVANCE = """
CREATE FUNCTION billing_chain_heads_advance() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    linked_to uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.last_record_id IS NOT NULL THEN
            RAISE EXCEPTION 'RN-F-07: la cabeza de la cadena nace vacía.'
                USING ERRCODE = 'KZF07';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'RN-F-07: la cabeza no cambia de cuenta.' USING ERRCODE = 'KZF07';
    END IF;
    IF NEW.last_record_id IS NOT DISTINCT FROM OLD.last_record_id THEN
        RETURN NEW;
    END IF;
    SELECT previous_record_id INTO linked_to FROM billing_records
        WHERE tenant_id = NEW.tenant_id AND id = NEW.last_record_id;
    IF NOT FOUND OR linked_to IS DISTINCT FROM OLD.last_record_id THEN
        RAISE EXCEPTION 'RN-F-07: la cabeza solo avanza al registro siguiente.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NEW;
END;
$$
"""

_REJECT_TRUNCATE = """
CREATE FUNCTION reject_truncate_of_fiscal_table() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'RN-F-02: la tabla % no se vacía.', TG_TABLE_NAME USING ERRCODE = 'KZF02';
END;
$$
"""


def upgrade() -> None:
    _create_tables()
    _secure_tables()
    _create_triggers()


def _create_tables() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("reference_price", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("is_material", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("origin IN ('manual', 'history')", name=op.f("ck_catalog_items_origin")),
        sa.CheckConstraint(
            "reference_price > 0", name=op.f("ck_catalog_items_reference_price_positive")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_catalog_items_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_items")),
    )
    op.create_index("ix_catalog_items_tenant_id", "catalog_items", ["tenant_id"], unique=False)
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tax_id", sa.String(length=9), nullable=True),
        sa.Column("tax_id_type", sa.String(length=8), nullable=True),
        sa.Column("tax_id_country", sa.String(length=2), nullable=True),
        sa.Column("address", sa.String(length=250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(tax_id IS NULL AND tax_id_type IS NULL AND tax_id_country IS NULL) OR (tax_id IS "
            "NOT NULL AND tax_id_type = 'nif' AND tax_id_country = 'ES')",
            name=op.f("ck_customers_tax_id_spanish_nif"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_customers_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "tax_id", name="uq_customers_tenant_id_tax_id"),
    )
    op.create_table(
        "professional",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tax_id", sa.String(length=9), nullable=True),
        sa.Column("address", sa.String(length=250), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_professional_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_professional")),
    )
    op.create_table(
        "series_counters",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("series", sa.String(length=10), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.Column("last_issue_date", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "(last_number = 0) = (last_issue_date IS NULL)",
            name=op.f("ck_series_counters_last_issue_date"),
        ),
        sa.CheckConstraint("last_number >= 0", name=op.f("ck_series_counters_last_number")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_series_counters_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("tenant_id", "series", "year", name=op.f("pk_series_counters")),
    )
    op.create_table(
        "quotes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("series", sa.String(length=10), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'rejected', 'expired', "
            "'partially_invoiced', 'invoiced')",
            name=op.f("ck_quotes_status"),
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_quotes_number_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_quotes_customer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_quotes_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quotes")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_quotes_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "series", "year", "number", name="uq_quotes_number"),
    )
    op.create_index(
        "ix_quotes_tenant_id_customer_id", "quotes", ["tenant_id", "customer_id"], unique=False
    )
    op.create_table(
        "quote_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recipient_type", sa.String(length=16), nullable=False),
        sa.Column("dwelling_over_two_years", sa.Boolean(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "recipient_type IN ('private', 'community', 'business')",
            name=op.f("ck_quote_versions_recipient_type"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_quote_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quote_id"],
            ["quotes.tenant_id", "quotes.id"],
            name="fk_quote_versions_quote",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_quote_versions_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_versions")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_quote_versions_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "quote_id", "version", name="uq_quote_versions_version"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("quote_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("invoice_type", sa.String(length=2), nullable=False),
        sa.Column("correction_type", sa.String(length=16), nullable=True),
        sa.Column("correction_reason", sa.String(length=500), nullable=True),
        sa.Column("phase_type", sa.String(length=16), nullable=True),
        sa.Column("series", sa.String(length=10), nullable=False),
        sa.Column("issue_year", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operation_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("regime_key", sa.String(length=2), nullable=False),
        sa.Column("operation_class", sa.String(length=2), nullable=False),
        sa.Column("tax_rate", sa.SmallInteger(), nullable=True),
        sa.Column("exemption_cause", sa.String(length=2), nullable=True),
        sa.Column("recipient_type", sa.String(length=16), nullable=True),
        sa.Column("dwelling_over_two_years", sa.Boolean(), nullable=True),
        sa.Column("gross_amount", sa.Integer(), nullable=True),
        sa.Column("withholding_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("guarantee_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("guarantee_due_date", sa.Date(), nullable=True),
        sa.Column("base_total", sa.Integer(), nullable=False),
        sa.Column("tax_total", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("withholding_amount", sa.Integer(), nullable=False),
        sa.Column("guarantee_amount", sa.Integer(), nullable=False),
        sa.Column("amount_due", sa.Integer(), nullable=False),
        sa.Column("issuer_name", sa.String(length=120), nullable=True),
        sa.Column("issuer_tax_id", sa.String(length=9), nullable=True),
        sa.Column("issuer_address", sa.String(length=250), nullable=True),
        sa.Column("recipient_name", sa.String(length=120), nullable=True),
        sa.Column("recipient_tax_id", sa.String(length=9), nullable=True),
        sa.Column("recipient_address", sa.String(length=250), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(invoice_type LIKE 'R%') = (correction_type IS NOT NULL) AND (correction_type IS "
            "NULL) = (correction_reason IS NULL) AND (correction_type IS NULL OR correction_type "
            "IN ('substitution', 'difference'))",
            name=op.f("ck_invoices_correction"),
        ),
        sa.CheckConstraint(
            "(operation_class = 'S1') = (tax_rate IS NOT NULL) AND (tax_rate IS NULL OR tax_rate "
            "IN (21, 10, 4))",
            name=op.f("ck_invoices_tax_rate"),
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND number IS NULL AND issue_year IS NULL AND issue_date IS NULL "
            "AND issued_at IS NULL AND issuer_name IS NULL AND issuer_tax_id IS NULL AND "
            "issuer_address IS NULL AND recipient_name IS NULL AND recipient_tax_id IS NULL AND "
            "recipient_address IS NULL) OR (status = 'issued' AND number >= 1 AND issue_date IS "
            "NOT NULL AND issue_year = EXTRACT(YEAR FROM issue_date) AND issued_at IS NOT NULL "
            "AND issuer_name IS NOT NULL AND issuer_tax_id IS NOT NULL AND issuer_address IS NOT "
            "NULL AND recipient_name IS NOT NULL AND recipient_tax_id IS NOT NULL AND "
            "recipient_address IS NOT NULL)",
            name=op.f("ck_invoices_issued_fields"),
        ),
        sa.CheckConstraint(
            "invoice_type IN ('F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5')",
            name=op.f("ck_invoices_invoice_type"),
        ),
        sa.CheckConstraint(
            "operation_class IN ('S1', 'S2', 'N1', 'N2')", name=op.f("ck_invoices_operation_class")
        ),
        sa.CheckConstraint(
            "phase_type IS NULL OR phase_type IN ('full', 'advance', 'progress', 'final')",
            name=op.f("ck_invoices_phase_type"),
        ),
        sa.CheckConstraint(
            "recipient_type IS NULL OR recipient_type IN ('private', 'community', 'business')",
            name=op.f("ck_invoices_recipient_type"),
        ),
        sa.CheckConstraint("status IN ('draft', 'issued')", name=op.f("ck_invoices_status")),
        sa.CheckConstraint(
            "(guarantee_pct IS NULL) = (guarantee_due_date IS NULL)",
            name=op.f("ck_invoices_guarantee"),
        ),
        sa.CheckConstraint(
            "total_amount = base_total + tax_total AND amount_due = total_amount - "
            "withholding_amount - guarantee_amount",
            name=op.f("ck_invoices_amounts"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_invoices_customer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quote_version_id"],
            ["quote_versions.tenant_id", "quote_versions.id"],
            name="fk_invoices_quote_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invoices_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_invoices_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "series", "issue_year", "number", name="uq_invoices_number"
        ),
    )
    op.create_index(
        "ix_invoices_tenant_id_customer_id", "invoices", ["tenant_id", "customer_id"], unique=False
    )
    op.create_index(
        "ix_invoices_tenant_id_quote_version_id",
        "invoices",
        ["tenant_id", "quote_version_id"],
        unique=False,
    )
    op.create_table(
        "quote_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("quote_version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=9, scale=3), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("price_source", sa.String(length=16), nullable=False),
        sa.Column("price_source_samples", sa.Integer(), nullable=True),
        sa.Column("price_source_reference_id", sa.Uuid(), nullable=True),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_material", sa.Boolean(), nullable=False),
        sa.Column("outside_works", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "(unit_price IS NULL) = (price_source = 'none')", name=op.f("ck_quote_lines_priced")
        ),
        sa.CheckConstraint(
            "price_source IN ('catalog', 'history_median', 'similar_quote', 'manual', 'none')",
            name=op.f("ck_quote_lines_price_source"),
        ),
        sa.CheckConstraint(
            "NOT (is_material AND outside_works)", name=op.f("ck_quote_lines_material_in_works")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_quote_lines_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quote_version_id"],
            ["quote_versions.tenant_id", "quote_versions.id"],
            name="fk_quote_lines_quote_version",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_quote_lines_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_lines")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_quote_lines_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "quote_version_id", "position", name="uq_quote_lines_position"
        ),
    )
    op.create_table(
        "billing_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("previous_record_id", sa.Uuid(), nullable=True),
        sa.Column("record_type", sa.String(length=16), nullable=False),
        sa.Column("is_correction", sa.Boolean(), nullable=False),
        sa.Column("prior_rejection", sa.Boolean(), nullable=False),
        sa.Column("issuer_tax_id", sa.String(length=9), nullable=False),
        sa.Column("series_number", sa.String(length=60), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("is_first", sa.Boolean(), nullable=False),
        sa.Column("prev_issuer_tax_id", sa.String(length=9), nullable=True),
        sa.Column("prev_series_number", sa.String(length=60), nullable=True),
        sa.Column("prev_issue_date", sa.Date(), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("system_name", sa.String(length=30), nullable=False),
        sa.Column("system_id", sa.String(length=2), nullable=False),
        sa.Column("system_version", sa.String(length=50), nullable=False),
        sa.Column("installation_number", sa.String(length=100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_ref", sa.String(length=60), nullable=True),
        sa.Column("canonical_json", sa.Text(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("submission_status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=20), nullable=True),
        sa.Column("error_description", sa.String(length=1500), nullable=True),
        sa.Column("submission_csv", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_with_incident", sa.Boolean(), nullable=False),
        sa.CheckConstraint("hash ~ '^[0-9A-F]{64}$'", name=op.f("ck_billing_records_hash_format")),
        sa.CheckConstraint(
            "record_type IN ('registration', 'cancellation')",
            name=op.f("ck_billing_records_record_type"),
        ),
        sa.CheckConstraint(
            "submission_status IN ('pending', 'accepted', 'accepted_with_errors', 'rejected')",
            name=op.f("ck_billing_records_submission_status"),
        ),
        sa.CheckConstraint(
            "(is_first AND previous_record_id IS NULL AND prev_issuer_tax_id IS NULL AND "
            "prev_series_number IS NULL AND prev_issue_date IS NULL AND prev_hash IS NULL) OR "
            "(NOT is_first AND previous_record_id IS NOT NULL AND prev_issuer_tax_id IS NOT NULL "
            "AND prev_series_number IS NOT NULL AND prev_issue_date IS NOT NULL AND prev_hash IS "
            "NOT NULL)",
            name=op.f("ck_billing_records_chain_link"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_billing_records_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "previous_record_id"],
            ["billing_records.tenant_id", "billing_records.id"],
            name="fk_billing_records_previous",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_billing_records_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_records")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_billing_records_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "previous_record_id",
            name="uq_billing_records_previous",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_billing_records_tenant_id_invoice_id",
        "billing_records",
        ["tenant_id", "invoice_id"],
        unique=False,
    )
    op.create_table(
        "invoice_corrections",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("corrective_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("rectified_invoice_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rectified_base", sa.Integer(), nullable=True),
        sa.Column("rectified_tax", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(rectified_base IS NULL) = (rectified_tax IS NULL)",
            name=op.f("ck_invoice_corrections_rectified"),
        ),
        sa.CheckConstraint(
            "corrective_invoice_id <> rectified_invoice_id",
            name=op.f("ck_invoice_corrections_not_itself"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "corrective_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_corrections_corrective",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "rectified_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_corrections_rectified",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invoice_corrections_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "corrective_invoice_id",
            "rectified_invoice_id",
            name=op.f("pk_invoice_corrections"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "corrective_invoice_id", "position", name="uq_invoice_corrections_position"
        ),
    )
    op.create_index(
        "ix_invoice_corrections_tenant_id_rectified_invoice_id",
        "invoice_corrections",
        ["tenant_id", "rectified_invoice_id"],
        unique=False,
    )
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=9, scale=3), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("discount_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("is_material", sa.Boolean(), nullable=False),
        sa.Column("outside_works", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=True),
        sa.Column("quote_line_id", sa.Uuid(), nullable=True),
        sa.Column("prior_invoice_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(origin IS NOT DISTINCT FROM 'quote') = (quote_line_id IS NOT NULL) AND (origin IS "
            "NOT DISTINCT FROM 'prior_invoice') = (prior_invoice_id IS NOT NULL)",
            name=op.f("ck_invoice_lines_origin_reference"),
        ),
        sa.CheckConstraint(
            "origin IS NULL OR origin IN ('quote', 'additional', 'prior_invoice')",
            name=op.f("ck_invoice_lines_origin"),
        ),
        sa.CheckConstraint(
            "NOT (is_material AND outside_works)", name=op.f("ck_invoice_lines_material_in_works")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_invoice_lines_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_lines_invoice",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "prior_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_lines_prior_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quote_line_id"],
            ["quote_lines.tenant_id", "quote_lines.id"],
            name="fk_invoice_lines_quote_line",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invoice_lines_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoice_lines")),
        sa.UniqueConstraint(
            "tenant_id", "invoice_id", "position", name="uq_invoice_lines_position"
        ),
    )
    op.create_index(
        "ix_invoice_lines_tenant_id_prior_invoice_id",
        "invoice_lines",
        ["tenant_id", "prior_invoice_id"],
        unique=False,
    )
    op.create_index(
        "ix_invoice_lines_tenant_id_quote_line_id",
        "invoice_lines",
        ["tenant_id", "quote_line_id"],
        unique=False,
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "method IN ('cash', 'card', 'transfer', 'bizum', 'cheque', 'deposit')",
            name=op.f("ck_payments_method"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_payments_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_payments_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    op.create_index(
        "ix_payments_tenant_id_invoice_id", "payments", ["tenant_id", "invoice_id"], unique=False
    )
    op.create_table(
        "billing_chain_heads",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("last_record_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "last_record_id"],
            ["billing_records.tenant_id", "billing_records.id"],
            name="fk_billing_chain_heads_last_record",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_billing_chain_heads_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_billing_chain_heads")),
    )


def _secure_tables() -> None:
    # Sin FORCE, como tenants: el propietario (migraciones y, en el futuro, la
    # función de mantenimiento del espacio de demostración) no queda filtrado.
    for table, privileges in _GRANTS.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = {_CURRENT_TENANT}) "
            f"WITH CHECK (tenant_id = {_CURRENT_TENANT})"
        )
        op.execute(f"GRANT {privileges} ON {table} TO {APP_ROLE}")


def _create_triggers() -> None:
    for function in (
        _INVOICES_IMMUTABLE,
        _CHILDREN_IMMUTABLE,
        _RECORDS_APPEND_ONLY,
        _RECORDS_CHECK_LINK,
        _HEADS_ADVANCE,
        _REJECT_TRUNCATE,
    ):
        op.execute(function)
    op.execute(
        "CREATE TRIGGER invoices_immutable_when_issued "
        "BEFORE UPDATE OR DELETE ON invoices "
        "FOR EACH ROW EXECUTE FUNCTION invoices_immutable_when_issued()"
    )
    op.execute(
        "CREATE TRIGGER invoice_lines_immutable_when_issued "
        "BEFORE INSERT OR UPDATE OR DELETE ON invoice_lines "
        "FOR EACH ROW EXECUTE FUNCTION invoice_children_immutable_when_issued('invoice_id')"
    )
    op.execute(
        "CREATE TRIGGER invoice_corrections_immutable_when_issued "
        "BEFORE INSERT OR UPDATE OR DELETE ON invoice_corrections "
        "FOR EACH ROW EXECUTE FUNCTION "
        "invoice_children_immutable_when_issued('corrective_invoice_id')"
    )
    op.execute(
        "CREATE TRIGGER billing_records_append_only "
        "BEFORE UPDATE OR DELETE ON billing_records "
        "FOR EACH ROW EXECUTE FUNCTION billing_records_append_only()"
    )
    op.execute(
        "CREATE TRIGGER billing_records_check_link "
        "BEFORE INSERT ON billing_records "
        "FOR EACH ROW EXECUTE FUNCTION billing_records_check_link()"
    )
    op.execute(
        "CREATE TRIGGER billing_chain_heads_advance "
        "BEFORE INSERT OR UPDATE ON billing_chain_heads "
        "FOR EACH ROW EXECUTE FUNCTION billing_chain_heads_advance()"
    )
    for table in _NO_TRUNCATE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_reject_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION reject_truncate_of_fiscal_table()"
        )


def downgrade() -> None:
    # Al borrar las tablas se van con ellas sus políticas y sus triggers; las
    # funciones se borran después. Los permisos se retiran antes, como en 0001.
    for table in _GRANTS:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.drop_table("billing_chain_heads")
    op.drop_index("ix_payments_tenant_id_invoice_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoice_lines_tenant_id_quote_line_id", table_name="invoice_lines")
    op.drop_index("ix_invoice_lines_tenant_id_prior_invoice_id", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index(
        "ix_invoice_corrections_tenant_id_rectified_invoice_id", table_name="invoice_corrections"
    )
    op.drop_table("invoice_corrections")
    op.drop_index("ix_billing_records_tenant_id_invoice_id", table_name="billing_records")
    op.drop_table("billing_records")
    op.drop_table("quote_lines")
    op.drop_index("ix_invoices_tenant_id_quote_version_id", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id_customer_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("quote_versions")
    op.drop_index("ix_quotes_tenant_id_customer_id", table_name="quotes")
    op.drop_table("quotes")
    op.drop_table("series_counters")
    op.drop_table("professional")
    op.drop_table("customers")
    op.drop_index("ix_catalog_items_tenant_id", table_name="catalog_items")
    op.drop_table("catalog_items")
    for function in _FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
