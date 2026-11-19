"""La cuenta deja de llevar el email como nombre (F-05 de la revisión del Bloque 1).

Revision ID: 0002_nombre_de_cuenta
Revises: 0001_cuentas
Create Date: 2026-11-18

- ``tenants.name`` admite NULL: la cuenta nace sin nombre y lo recibe con los
  datos del profesional.
- Se vacían los nombres existentes, que eran copias del email del usuario: un
  dato personal duplicado que además podía superar los 200 caracteres.
- La vuelta atrás deja la cadena vacía en vez de NULL y no recupera los emails.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_nombre_de_cuenta"
down_revision: str | Sequence[str] | None = "0001_cuentas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("tenants", "name", existing_type=sa.String(length=200), nullable=True)
    # El propietario no queda filtrado por RLS (tenants no tiene FORCE).
    op.execute("UPDATE tenants SET name = NULL")


def downgrade() -> None:
    op.execute("UPDATE tenants SET name = '' WHERE name IS NULL")
    op.alter_column("tenants", "name", existing_type=sa.String(length=200), nullable=False)
