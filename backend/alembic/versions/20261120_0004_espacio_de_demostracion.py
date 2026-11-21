"""Endurece ``tenants`` para el espacio de demostración (RF-CF-04, S3-01, I-5).

Revision ID: 0004_espacio_de_demostracion
Revises: 0003_facturacion
Create Date: 2026-11-20

- **Antes de nada, revisa las filas que ya hay** (S3-R-05), con ``tenants``
  bloqueada (``ACCESS EXCLUSIVE``) hasta el final: ningún espacio de
  demostración sin cuenta padre, ninguno dentro de otro espacio y ninguna
  cuenta con dos. Si
  alguna fila lo incumple, la migración falla (``KZF14``) con un mensaje que
  solo dice cuántas hay de cada caso, sin ids ni nombres, y no cambia nada.
- **Un espacio por cuenta.** El índice de ``parent_tenant_id`` pasa a ser
  único (``uq_tenants_parent_tenant_id``): una cuenta no tiene dos espacios
  de demostración aunque lleven ids distintos.
- **El espacio se da de alta desde su cuenta padre.** Política nueva
  ``demo_space_from_parent`` (solo ``INSERT``): con la cuenta padre fijada en
  ``app.tenant_id`` se puede insertar su espacio, cuyo id no es el fijado.
  ``tenant_isolation`` no cambia: leer, actualizar y dar de alta una cuenta
  normal siguen exigiendo ``id`` igual a la cuenta fijada.
- **Trigger ``tenants_check_hierarchy``** (``BEFORE INSERT OR UPDATE``):

  - al insertar un espacio de demostración, la cuenta padre tiene que existir,
    verse desde la transacción y ser ``standard``;
  - al actualizar, ni el ``id`` ni el ``kind`` ni el ``parent_tenant_id``
    cambian.

  Actúa también para el propietario, como los triggers de la 0003.
- **``kapataz_app`` solo actualiza ``name``:** se retira ``UPDATE`` de la tabla
  y se concede ``UPDATE (name)``. Basta también para ``SELECT … FOR UPDATE``.

Cómo ve el trigger a la cuenta padre: corre con los permisos de quien inserta
(``SECURITY INVOKER``, lo normal), así que RLS le aplica. Para la app, la
cuenta padre solo es visible si es la cuenta fijada; si es de otra cuenta o no
existe, el trigger no la encuentra y responde lo mismo en los dos casos. Así
el trigger exige que el padre sea la cuenta fijada sin servir de oráculo de
existencia de otras cuentas, y sin ``SECURITY DEFINER``: no hace falta saltarse
RLS para nada. El trigger es ``BEFORE``: falla antes de que se evalúen la
política (``WITH CHECK``) y la clave foránea, que sí distinguiría un padre
inexistente (``23503``) de uno ajeno. El propietario no queda filtrado por RLS
(``tenants`` no tiene ``FORCE``) y ve cualquier cuenta: para él el trigger
comprueba que el padre exista y sea ``standard``.

Por la rama de ``tenant_isolation`` (id igual a la cuenta fijada) no entra un
espacio de demostración: su padre tendría que ser la cuenta fijada, es decir,
él mismo, que aún no existe.

Lo que no se exige: que ``id = uuid5(espacio de nombres, parent_tenant_id)``
(``demo_tenant_id`` del dominio). UUIDv5 usa SHA-1, y PostgreSQL solo trae de
serie ``md5`` y la familia SHA-2; SHA-1 necesita ``pgcrypto`` o ``uuid-ossp``,
extensiones que el despliegue no garantiza. El índice único ya asegura un
espacio por cuenta; si un fallo de la app diera de alta uno con otro id, la
cuenta no lo encontraría y tampoco podría crear el bueno.

``search_path`` fijo y tablas con su esquema, como en la 0003 (S2-01).

Código de error (SQLSTATE, clase ``KZ``): ``KZF14``. En la 0003, ``KZF00`` es
``TRUNCATE`` y ``KZFnn`` sigue el número de la regla ``RN-F-nn``, que hoy
llega a ``RN-F-13``; ``KZF14`` es el siguiente libre fuera de ese tramo. Lo
usan todas las reglas de este trigger. Si se añade una ``RN-F-14`` con su
propio código, tendrá que tomar otro.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_espacio_de_demostracion"
down_revision: str | Sequence[str] | None = "0003_facturacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "kapataz_app"
_CURRENT_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_ERRCODE = "KZF14"

_CHECK_HIERARCHY = f"""
CREATE FUNCTION public.tenants_check_hierarchy()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    parent_kind text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
            OR NEW.kind IS DISTINCT FROM OLD.kind
            OR NEW.parent_tenant_id IS DISTINCT FROM OLD.parent_tenant_id THEN
            RAISE EXCEPTION 'RF-CF-04: el id, el tipo y la cuenta padre de una cuenta no cambian.'
                USING ERRCODE = '{_ERRCODE}';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.kind = 'demo' THEN
        -- Con RLS: para la app, solo la cuenta fijada. Ajena o inexistente,
        -- el mismo error.
        SELECT t.kind INTO parent_kind FROM public.tenants t WHERE t.id = NEW.parent_tenant_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'RF-CF-04: la cuenta padre no existe o no es la cuenta fijada.'
                USING ERRCODE = '{_ERRCODE}';
        END IF;
        IF parent_kind IS DISTINCT FROM 'standard' THEN
            RAISE EXCEPTION 'RF-CF-04: un espacio de demostración no tiene otro dentro.'
                USING ERRCODE = '{_ERRCODE}';
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""

# ACCESS EXCLUSIVE desde el principio: es el que pide DROP INDEX, el más fuerte
# de la migración (CREATE TRIGGER pide SHARE ROW EXCLUSIVE). Con uno más débil,
# la migración tendría que subir de nivel a mitad: si entre tanto una
# transacción que ya ha leído tenants espera para escribir en ella, cada una
# espera a la otra y PostgreSQL aborta una por interbloqueo. Pidiéndolo de
# entrada, la migración espera a que acaben las que ya leen y, desde que lo
# obtiene, nadie lee ni escribe tenants hasta el COMMIT. La migración es corta.
_LOCK_TENANTS = "LOCK TABLE public.tenants IN ACCESS EXCLUSIVE MODE"

# Las filas que ya hay tienen que cumplir lo que el trigger y el índice único
# exigirán a las nuevas: el trigger no revisa las existentes, y el índice
# fallaría con un DETAIL que lleva el id repetido. Se informa solo de cuántas
# hay de cada caso, sin ids ni nombres; la migración no cambia datos.
_CHECK_EXISTING_ROWS = f"""
DO $$
DECLARE
    without_parent bigint;
    inside_demo bigint;
    repeated_parents bigint;
BEGIN
    SELECT count(*) INTO without_parent FROM public.tenants d
     WHERE d.kind = 'demo'
       AND NOT EXISTS (SELECT 1 FROM public.tenants p WHERE p.id = d.parent_tenant_id);
    SELECT count(*) INTO inside_demo FROM public.tenants d
      JOIN public.tenants p ON p.id = d.parent_tenant_id
     WHERE d.kind = 'demo' AND p.kind IS DISTINCT FROM 'standard';
    SELECT count(*) INTO repeated_parents FROM (
        SELECT parent_tenant_id FROM public.tenants
         WHERE parent_tenant_id IS NOT NULL
         GROUP BY parent_tenant_id HAVING count(*) > 1
    ) AS r;
    IF without_parent + inside_demo + repeated_parents > 0 THEN
        RAISE EXCEPTION 'RF-CF-04: la migración 0004 no se aplica: hay espacios de '
            'demostración que no cumplen sus reglas. Espacios sin cuenta padre: %; '
            'espacios dentro de otro espacio: %; cuentas con más de un espacio: %.',
            without_parent, inside_demo, repeated_parents
            USING ERRCODE = '{_ERRCODE}',
                  HINT = 'Revisa las filas de tenants con kind = ''demo'' y corrige o borra '
                         'las que sobren antes de volver a migrar.';
    END IF;
END
$$
"""

_TRIGGER = (
    "CREATE TRIGGER tenants_check_hierarchy "
    "BEFORE INSERT OR UPDATE ON public.tenants "
    "FOR EACH ROW EXECUTE FUNCTION public.tenants_check_hierarchy()"
)

_POLICY = (
    "CREATE POLICY demo_space_from_parent ON public.tenants FOR INSERT "
    f"WITH CHECK (kind = 'demo' AND parent_tenant_id = {_CURRENT_TENANT})"
)


def upgrade() -> None:
    # Hasta el final de la migración nadie toca tenants: lo que se comprueba
    # ahora sigue valiendo cuando el índice y el trigger ya están.
    op.execute(_LOCK_TENANTS)
    op.execute(_CHECK_EXISTING_ROWS)
    op.drop_index("ix_tenants_parent_tenant_id", table_name="tenants")
    op.create_index("uq_tenants_parent_tenant_id", "tenants", ["parent_tenant_id"], unique=True)
    op.execute(_CHECK_HIERARCHY)
    op.execute(_TRIGGER)
    op.execute(_POLICY)
    # Al retirar UPDATE de la tabla se retiran también los de columna: primero
    # se retira y después se concede el de name.
    op.execute(f"REVOKE UPDATE ON public.tenants FROM {APP_ROLE}")
    op.execute(f"GRANT UPDATE (name) ON public.tenants TO {APP_ROLE}")


def downgrade() -> None:
    # El mismo bloqueo de entrada que upgrade() y por el mismo motivo: DROP
    # POLICY, DROP TRIGGER y DROP INDEX piden ACCESS EXCLUSIVE.
    op.execute(_LOCK_TENANTS)
    op.execute(f"REVOKE UPDATE ON public.tenants FROM {APP_ROLE}")
    op.execute(f"GRANT UPDATE ON public.tenants TO {APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS demo_space_from_parent ON public.tenants")
    op.execute("DROP TRIGGER IF EXISTS tenants_check_hierarchy ON public.tenants")
    op.execute("DROP FUNCTION IF EXISTS public.tenants_check_hierarchy()")
    op.drop_index("uq_tenants_parent_tenant_id", table_name="tenants")
    op.create_index("ix_tenants_parent_tenant_id", "tenants", ["parent_tenant_id"], unique=False)
