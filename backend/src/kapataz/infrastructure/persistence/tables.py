"""Tablas de SQLAlchemy 2 (estilo tipado). Las migraciones las crean y deben coincidir.

Las filas no salen de ``infrastructure/persistence``: el repositorio las
convierte en entidades del dominio.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kapataz.domain.billing.money import Money
from kapataz.infrastructure.persistence.money import Cents

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Tablas sin RLS porque se leen antes de saber la cuenta (ADR-024, arquitectura §5.4).
# Una prueba de integración falla si aparece otra tabla sin RLS.
GLOBAL_TABLES_WITHOUT_RLS = frozenset(
    {
        "users",
        "sessions",
        "email_verifications",
        "subscriptions",
        "payment_events",
        "platform_settings",
        "platform_admins",
        "platform_audit_events",
    }
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("kind IN ('standard', 'demo')", name="kind"),
        CheckConstraint("(kind = 'demo') = (parent_tenant_id IS NOT NULL)", name="demo_has_parent"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    parent_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(btrim(email))", name="email_normalized"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionRow(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # SHA-256 en hexadecimal del token de la cookie; el token en claro no se guarda.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationRow(Base):
    __tablename__ = "email_verifications"
    __table_args__ = (Index("ix_email_verifications_user_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ facturación
#
# Toda tabla de negocio lleva tenant_id con RLS (ADR-024). Las referencias entre
# tablas de negocio son claves foráneas compuestas (tenant_id, …) contra un
# UNIQUE (tenant_id, id) de la tabla referida: la base de datos impide enlazar
# filas de cuentas distintas aunque el código se equivoque (RNF-13).
# Los importes son céntimos en INTEGER (ADR-009, ``Cents``); los porcentajes y
# las cantidades no son importes y van en NUMERIC con la escala del dominio.
# Ninguna tabla de facturación borra en cascada desde ``tenants``: las facturas
# emitidas se conservan (RN-12) y su borrado no puede ser un efecto secundario.

_RECIPIENT_TYPES = "('private', 'community', 'business')"
_QUANTITY = Numeric(9, 3)
_PERCENTAGE = Numeric(5, 2)


class ProfessionalRow(Base):
    """Datos del emisor: una fila por cuenta (RF-CF-01)."""

    __tablename__ = "professional"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tax_id: Mapped[str | None] = mapped_column(String(9))
    address: Mapped[str | None] = mapped_column(String(250))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerRow(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_customers_tenant_id_id"),
        # El NIF es único por cuenta cuando existe: los NULL no chocan entre sí.
        UniqueConstraint("tenant_id", "tax_id", name="uq_customers_tenant_id_tax_id"),
        # La v1 solo admite NIF español (§1.4). Los identificadores extranjeros
        # (IDType 02 a 07 de la AEAT) ampliarán esta regla con su migración.
        CheckConstraint(
            "(tax_id IS NULL AND tax_id_type IS NULL AND tax_id_country IS NULL) "
            "OR (tax_id IS NOT NULL AND tax_id_type = 'nif' AND tax_id_country = 'ES')",
            name="tax_id_spanish_nif",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(120))
    tax_id: Mapped[str | None] = mapped_column(String(9))
    tax_id_type: Mapped[str | None] = mapped_column(String(8))
    tax_id_country: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CatalogItemRow(Base):
    __tablename__ = "catalog_items"
    __table_args__ = (
        Index("ix_catalog_items_tenant_id", "tenant_id"),
        CheckConstraint("origin IN ('manual', 'history')", name="origin"),
        CheckConstraint("reference_price > 0", name="reference_price_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    concept: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(20))
    reference_price: Mapped[Money | None] = mapped_column(Cents())
    origin: Mapped[str] = mapped_column(String(16))
    is_material: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteRow(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_quotes_tenant_id_id"),
        UniqueConstraint("tenant_id", "series", "year", "number", name="uq_quotes_number"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_quotes_customer",
        ),
        Index("ix_quotes_tenant_id_customer_id", "tenant_id", "customer_id"),
        CheckConstraint(
            "status IN ('draft', 'sent', 'accepted', 'rejected', 'expired', "
            "'partially_invoiced', 'invoiced')",
            name="status",
        ),
        CheckConstraint("number >= 1", name="number_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[UUID]
    series: Mapped[str] = mapped_column(String(10))
    year: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteVersionRow(Base):
    __tablename__ = "quote_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_quote_versions_tenant_id_id"),
        UniqueConstraint("tenant_id", "quote_id", "version", name="uq_quote_versions_version"),
        ForeignKeyConstraint(
            ["tenant_id", "quote_id"],
            ["quotes.tenant_id", "quotes.id"],
            name="fk_quote_versions_quote",
            ondelete="CASCADE",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(f"recipient_type IN {_RECIPIENT_TYPES}", name="recipient_type"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    quote_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(Integer)
    recipient_type: Mapped[str] = mapped_column(String(16))
    dwelling_over_two_years: Mapped[bool | None] = mapped_column(Boolean)
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuoteLineRow(Base):
    __tablename__ = "quote_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_quote_lines_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "quote_version_id", "position", name="uq_quote_lines_position"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "quote_version_id"],
            ["quote_versions.tenant_id", "quote_versions.id"],
            name="fk_quote_lines_quote_version",
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "price_source IN ('catalog', 'history_median', 'similar_quote', 'manual', 'none')",
            name="price_source",
        ),
        CheckConstraint("(unit_price IS NULL) = (price_source = 'none')", name="priced"),
        CheckConstraint("NOT (is_material AND outside_works)", name="material_in_works"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    quote_version_id: Mapped[UUID]
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(1000))
    quantity: Mapped[Decimal] = mapped_column(_QUANTITY)
    unit_price: Mapped[Money | None] = mapped_column(Cents())
    price_source: Mapped[str] = mapped_column(String(16))
    price_source_samples: Mapped[int | None] = mapped_column(Integer)
    # Concepto del catálogo o presupuesto parecido que se cita (RN-06). Sin
    # clave foránea: puede apuntar a dos tablas distintas.
    price_source_reference_id: Mapped[UUID | None]
    discount_pct: Mapped[Decimal | None] = mapped_column(_PERCENTAGE)
    is_material: Mapped[bool] = mapped_column(Boolean)
    outside_works: Mapped[bool] = mapped_column(Boolean)


class InvoiceRow(Base):
    """Factura o rectificativa. Las columnas de importe son copia de lo que calcula el dominio."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_invoices_tenant_id_id"),
        # RN-F-01: un número por cuenta, serie y año. Los borradores no tienen
        # número y los NULL no chocan entre sí.
        UniqueConstraint("tenant_id", "series", "issue_year", "number", name="uq_invoices_number"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_invoices_customer",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "quote_version_id"],
            ["quote_versions.tenant_id", "quote_versions.id"],
            name="fk_invoices_quote_version",
        ),
        Index("ix_invoices_tenant_id_customer_id", "tenant_id", "customer_id"),
        Index("ix_invoices_tenant_id_quote_version_id", "tenant_id", "quote_version_id"),
        CheckConstraint("status IN ('draft', 'issued')", name="status"),
        CheckConstraint(
            "invoice_type IN ('F1', 'F2', 'F3', 'R1', 'R2', 'R3', 'R4', 'R5')", name="invoice_type"
        ),
        CheckConstraint(
            "(invoice_type LIKE 'R%') = (correction_type IS NOT NULL) "
            "AND (correction_type IS NULL) = (correction_reason IS NULL) "
            "AND (correction_type IS NULL OR correction_type IN ('substitution', 'difference'))",
            name="correction",
        ),
        CheckConstraint(
            "phase_type IS NULL OR phase_type IN ('full', 'advance', 'progress', 'final')",
            name="phase_type",
        ),
        CheckConstraint("operation_class IN ('S1', 'S2', 'N1', 'N2')", name="operation_class"),
        CheckConstraint(
            "(operation_class = 'S1') = (tax_rate IS NOT NULL) "
            "AND (tax_rate IS NULL OR tax_rate IN (21, 10, 4))",
            name="tax_rate",
        ),
        CheckConstraint(
            f"recipient_type IS NULL OR recipient_type IN {_RECIPIENT_TYPES}",
            name="recipient_type",
        ),
        # RN-F-13: el borrador que sale de un presupuesto toma el destinatario y
        # la vivienda de su versión, que los copia al emitir; una emitida los
        # lleva siempre, y la vivienda solo falta si el destinatario es empresa.
        CheckConstraint(
            "(status = 'draft' AND (quote_version_id IS NULL "
            "OR (recipient_type IS NULL AND dwelling_over_two_years IS NULL))) "
            "OR (status = 'issued' AND recipient_type IS NOT NULL "
            "AND (recipient_type = 'business' OR dwelling_over_two_years IS NOT NULL))",
            name="works_recipient",
        ),
        CheckConstraint("(guarantee_pct IS NULL) = (guarantee_due_date IS NULL)", name="guarantee"),
        # Defensa en profundidad (ADR-009): los importes los calcula el dominio
        # con Decimal; la base de datos solo comprueba que cuadran entre sí.
        CheckConstraint(
            "total_amount = base_total + tax_total "
            "AND amount_due = total_amount - withholding_amount - guarantee_amount",
            name="amounts",
        ),
        # Un borrador no tiene número, fecha de expedición ni partes; una
        # emitida lo tiene todo (RF-FA-02, RN-F-06).
        CheckConstraint(
            "(status = 'draft' AND number IS NULL AND issue_year IS NULL "
            "AND issue_date IS NULL AND issued_at IS NULL "
            "AND issuer_name IS NULL AND issuer_tax_id IS NULL AND issuer_address IS NULL "
            "AND recipient_name IS NULL AND recipient_tax_id IS NULL "
            "AND recipient_address IS NULL) "
            "OR (status = 'issued' AND number >= 1 AND issue_date IS NOT NULL "
            "AND issue_year = EXTRACT(YEAR FROM issue_date) AND issued_at IS NOT NULL "
            "AND issuer_name IS NOT NULL AND issuer_tax_id IS NOT NULL "
            "AND issuer_address IS NOT NULL AND recipient_name IS NOT NULL "
            "AND recipient_tax_id IS NOT NULL AND recipient_address IS NOT NULL)",
            name="issued_fields",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[UUID]
    quote_version_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(8))
    invoice_type: Mapped[str] = mapped_column(String(2))
    correction_type: Mapped[str | None] = mapped_column(String(16))
    correction_reason: Mapped[str | None] = mapped_column(String(500))
    phase_type: Mapped[str | None] = mapped_column(String(16))
    series: Mapped[str] = mapped_column(String(10))
    issue_year: Mapped[int | None] = mapped_column(Integer)
    number: Mapped[int | None] = mapped_column(Integer)
    issue_date: Mapped[date | None] = mapped_column(Date)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operation_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(500))
    regime_key: Mapped[str] = mapped_column(String(2))
    operation_class: Mapped[str] = mapped_column(String(2))
    tax_rate: Mapped[int | None] = mapped_column(SmallInteger)
    exemption_cause: Mapped[str | None] = mapped_column(String(2))
    recipient_type: Mapped[str | None] = mapped_column(String(16))
    dwelling_over_two_years: Mapped[bool | None] = mapped_column(Boolean)
    gross_amount: Mapped[Money | None] = mapped_column(Cents())
    withholding_pct: Mapped[Decimal | None] = mapped_column(_PERCENTAGE)
    guarantee_pct: Mapped[Decimal | None] = mapped_column(_PERCENTAGE)
    guarantee_due_date: Mapped[date | None] = mapped_column(Date)
    base_total: Mapped[Money] = mapped_column(Cents())
    tax_total: Mapped[Money] = mapped_column(Cents())
    total_amount: Mapped[Money] = mapped_column(Cents())
    withholding_amount: Mapped[Money] = mapped_column(Cents())
    guarantee_amount: Mapped[Money] = mapped_column(Cents())
    amount_due: Mapped[Money] = mapped_column(Cents())
    issuer_name: Mapped[str | None] = mapped_column(String(120))
    issuer_tax_id: Mapped[str | None] = mapped_column(String(9))
    issuer_address: Mapped[str | None] = mapped_column(String(250))
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    recipient_tax_id: Mapped[str | None] = mapped_column(String(9))
    recipient_address: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvoiceLineRow(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_id", "position", name="uq_invoice_lines_position"),
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_lines_invoice",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "quote_line_id"],
            ["quote_lines.tenant_id", "quote_lines.id"],
            name="fk_invoice_lines_quote_line",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "prior_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_lines_prior_invoice",
        ),
        Index("ix_invoice_lines_tenant_id_quote_line_id", "tenant_id", "quote_line_id"),
        Index("ix_invoice_lines_tenant_id_prior_invoice_id", "tenant_id", "prior_invoice_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("NOT (is_material AND outside_works)", name="material_in_works"),
        CheckConstraint(
            "origin IS NULL OR origin IN ('quote', 'additional', 'prior_invoice')", name="origin"
        ),
        CheckConstraint(
            "(origin IS NOT DISTINCT FROM 'quote') = (quote_line_id IS NOT NULL) "
            "AND (origin IS NOT DISTINCT FROM 'prior_invoice') = (prior_invoice_id IS NOT NULL)",
            name="origin_reference",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    invoice_id: Mapped[UUID]
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(1000))
    quantity: Mapped[Decimal] = mapped_column(_QUANTITY)
    unit_price: Mapped[Money] = mapped_column(Cents())
    discount_pct: Mapped[Decimal | None] = mapped_column(_PERCENTAGE)
    is_material: Mapped[bool] = mapped_column(Boolean)
    outside_works: Mapped[bool] = mapped_column(Boolean)
    origin: Mapped[str | None] = mapped_column(String(16))
    quote_line_id: Mapped[UUID | None]
    prior_invoice_id: Mapped[UUID | None]


class InvoiceCorrectionRow(Base):
    """Cada factura que rectifica una rectificativa (RN-F-03)."""

    __tablename__ = "invoice_corrections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "corrective_invoice_id", "position", name="uq_invoice_corrections_position"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "corrective_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_corrections_corrective",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "rectified_invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_invoice_corrections_rectified",
        ),
        Index(
            "ix_invoice_corrections_tenant_id_rectified_invoice_id",
            "tenant_id",
            "rectified_invoice_id",
        ),
        CheckConstraint("(rectified_base IS NULL) = (rectified_tax IS NULL)", name="rectified"),
        CheckConstraint("corrective_invoice_id <> rectified_invoice_id", name="not_itself"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    corrective_invoice_id: Mapped[UUID] = mapped_column(primary_key=True)
    rectified_invoice_id: Mapped[UUID] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(Integer)
    rectified_base: Mapped[Money | None] = mapped_column(Cents())
    rectified_tax: Mapped[Money | None] = mapped_column(Cents())


class SeriesCounterRow(Base):
    """Contador por cuenta, serie y año; se bloquea con FOR UPDATE al emitir (RN-F-01)."""

    __tablename__ = "series_counters"
    __table_args__ = (
        CheckConstraint("last_number >= 0", name="last_number"),
        CheckConstraint("(last_number = 0) = (last_issue_date IS NULL)", name="last_issue_date"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    series: Mapped[str] = mapped_column(String(10), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer)
    last_issue_date: Mapped[date | None] = mapped_column(Date)


class BillingRecordRow(Base):
    """Registro de facturación (RN-F-07). Contenido y huella tal como los produce el dominio."""

    __tablename__ = "billing_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_billing_records_tenant_id_id"),
        # Una sola cadena por cuenta: dos registros no pueden seguir al mismo, y
        # solo uno puede ser el primero (con NULLS NOT DISTINCT, NULL cuenta como
        # un valor más).
        UniqueConstraint(
            "tenant_id",
            "previous_record_id",
            name="uq_billing_records_previous",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_billing_records_invoice",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "previous_record_id"],
            ["billing_records.tenant_id", "billing_records.id"],
            name="fk_billing_records_previous",
        ),
        Index("ix_billing_records_tenant_id_invoice_id", "tenant_id", "invoice_id"),
        # RN-F-07: un solo alta por factura; las demás altas son subsanaciones
        # (is_correction, «Subsanacion» de la AEAT).
        Index(
            "uq_billing_records_registration",
            "tenant_id",
            "invoice_id",
            unique=True,
            postgresql_where=text("record_type = 'registration' AND NOT is_correction"),
        ),
        CheckConstraint("record_type IN ('registration', 'cancellation')", name="record_type"),
        CheckConstraint(
            "submission_status IN ('pending', 'accepted', 'accepted_with_errors', 'rejected')",
            name="submission_status",
        ),
        CheckConstraint("hash ~ '^[0-9A-F]{64}$'", name="hash_format"),
        CheckConstraint(
            "(is_first AND previous_record_id IS NULL AND prev_issuer_tax_id IS NULL "
            "AND prev_series_number IS NULL AND prev_issue_date IS NULL AND prev_hash IS NULL) "
            "OR (NOT is_first AND previous_record_id IS NOT NULL "
            "AND prev_issuer_tax_id IS NOT NULL AND prev_series_number IS NOT NULL "
            "AND prev_issue_date IS NOT NULL AND prev_hash IS NOT NULL)",
            name="chain_link",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    invoice_id: Mapped[UUID]
    # Registro anterior de la cadena: lo comprueba el trigger de enlace al insertar.
    previous_record_id: Mapped[UUID | None]
    record_type: Mapped[str] = mapped_column(String(16))
    is_correction: Mapped[bool] = mapped_column(Boolean)
    prior_rejection: Mapped[bool] = mapped_column(Boolean)
    issuer_tax_id: Mapped[str] = mapped_column(String(9))
    series_number: Mapped[str] = mapped_column(String(60))
    issue_date: Mapped[date] = mapped_column(Date)
    is_first: Mapped[bool] = mapped_column(Boolean)
    prev_issuer_tax_id: Mapped[str | None] = mapped_column(String(9))
    prev_series_number: Mapped[str | None] = mapped_column(String(60))
    prev_issue_date: Mapped[date | None] = mapped_column(Date)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    system_name: Mapped[str] = mapped_column(String(30))
    system_id: Mapped[str] = mapped_column(String(2))
    system_version: Mapped[str] = mapped_column(String(50))
    installation_number: Mapped[str] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    external_ref: Mapped[str | None] = mapped_column(String(60))
    # Texto, no JSONB: JSONB reordena las claves y quita espacios, y el
    # contenido tiene que conservarse tal como se calculó la huella.
    canonical_json: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String(64))
    # Columnas de envío: las únicas que el trigger deja cambiar (Bloque 12).
    submission_status: Mapped[str] = mapped_column(String(24))
    error_code: Mapped[str | None] = mapped_column(String(20))
    error_description: Mapped[str | None] = mapped_column(String(1500))
    submission_csv: Mapped[str | None] = mapped_column(String(100))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_with_incident: Mapped[bool] = mapped_column(Boolean)


class BillingChainHeadRow(Base):
    """Cabeza de la cadena de la cuenta: solo el enlace al último registro (RN-F-07)."""

    __tablename__ = "billing_chain_heads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "last_record_id"],
            ["billing_records.tenant_id", "billing_records.id"],
            name="fk_billing_chain_heads_last_record",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    last_record_id: Mapped[UUID | None]


class PaymentRow(Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "invoice_id"],
            ["invoices.tenant_id", "invoices.id"],
            name="fk_payments_invoice",
        ),
        Index("ix_payments_tenant_id_invoice_id", "tenant_id", "invoice_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "method IN ('cash', 'card', 'transfer', 'bizum', 'cheque', 'deposit')", name="method"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"))
    invoice_id: Mapped[UUID]
    amount: Mapped[Money] = mapped_column(Cents())
    paid_at: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
