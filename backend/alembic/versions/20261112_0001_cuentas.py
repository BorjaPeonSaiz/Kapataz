"""Cuentas: tenants, users, sessions y email_verifications, con RLS en tenants.

Revision ID: 0001_cuentas
Revises:
Create Date: 2026-11-12

- ``tenants`` lleva RLS: solo se ve la cuenta fijada con ``app.tenant_id``.
- ``users``, ``sessions`` y ``email_verifications`` son tablas globales sin RLS:
  se leen antes de saber la cuenta (al iniciar sesión, al validar la cookie y
  al verificar el email). Lista cerrada en ADR-024.
- El rol de la app (``kapataz_app``) recibe solo los permisos que usa. Lo crea
  el script de inicialización de PostgreSQL, sin BYPASSRLS.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_cuentas"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "kapataz_app"

# NULLIF: si la variable se fijó antes en la sesión, current_setting devuelve ''
# en vez de NULL, y ''::uuid fallaría. Sin cuenta fijada, ninguna fila.
_CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("parent_tenant_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('standard', 'demo')", name=op.f("ck_tenants_kind")),
        sa.CheckConstraint(
            "(kind = 'demo') = (parent_tenant_id IS NOT NULL)",
            name=op.f("ck_tenants_demo_has_parent"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenants_parent_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_index(
        op.f("ix_tenants_parent_tenant_id"), "tenants", ["parent_tenant_id"], unique=False
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("email = lower(btrim(email))", name=op.f("ck_users_email_normalized")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_users_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_verifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verifications")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_verifications_token_hash")),
    )
    op.create_index(
        "ix_email_verifications_user_id", "email_verifications", ["user_id"], unique=False
    )

    # RLS en tenants. Sin FORCE: el propietario (migraciones y, en el futuro, la
    # función de mantenimiento del espacio de demostración) no queda filtrado.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON tenants "
        f"USING (id = {_CURRENT_TENANT}) "
        f"WITH CHECK (id = {_CURRENT_TENANT})"
    )

    # Permisos mínimos del rol de la app. UPDATE también lo exige SELECT ... FOR UPDATE.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table in ("tenants", "users", "sessions", "email_verifications"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in ("email_verifications", "sessions", "users", "tenants"):
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenants")
    op.drop_index(op.f("ix_tenants_parent_tenant_id"), table_name="tenants")
    op.drop_table("tenants")
