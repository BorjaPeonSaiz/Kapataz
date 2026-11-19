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

Triggers, que actúan también para el propietario (RN-F-01 a RN-F-04, RN-F-07,
RN-F-12):

- ``invoices``: nace en borrador; con ``status = 'issued'``, ni ``UPDATE`` ni
  ``DELETE``. Al pasar a emitida, un trigger diferido (se comprueba al
  confirmar la transacción) exige que el contador de su serie y año haya
  avanzado justo hasta su número y su fecha, y que exista su registro de alta.
- ``invoice_lines`` e ``invoice_corrections``: ni altas, ni cambios, ni
  bajas si su factura está emitida. Bloquean la fila de la factura con
  ``FOR SHARE``, así que no pueden cruzarse con una emisión en curso. La
  factura que citan (la rectificada, o la fase anterior que se descuenta)
  tiene que estar emitida.
- ``series_counters``: nace a cero y solo avanza de uno en uno, sin que la
  fecha retroceda ni salga de su año. Cada avance, diferido, exige la factura
  emitida con ese número y esa fecha: no se dejan huecos sin emitir.
- ``billing_records``: solo de facturas emitidas, con el emisor, el número y
  la fecha de su factura, y un solo alta por factura que no sea subsanación
  (índice único parcial). Sin ``DELETE`` y sin ``UPDATE`` salvo en las
  columnas de envío. Al insertar, el enlace (``prev_*``) tiene que copiar el
  registro anterior y, al confirmar, la cabeza de la cadena tiene que haber
  llegado hasta él. La huella no se comprueba: la calcula el dominio.
- ``billing_chain_heads``: nace vacía y solo avanza al registro que sigue al
  actual.
- ``TRUNCATE`` rechazado en las cuatro tablas fiscales, en los contadores, en la
  cabeza de la cadena y en los cobros: vaciarlas nunca es una operación normal.

Las comprobaciones nuevas son triggers ``AFTER``: RLS (``WITH CHECK``), las
restricciones y las claves foráneas se evalúan antes, así que un intento desde
otra cuenta sigue fallando por RLS o por la clave foránea, no por el trigger.

Códigos de error (SQLSTATE, clase propia ``KZ``): ``KZF01`` numeración,
``KZF02`` factura emitida inmutable, ``KZF03`` rectificada no emitida,
``KZF04`` fecha del contador, ``KZF07`` cadena de registros, ``KZF12`` fase
anterior no emitida y ``KZF00`` para ``TRUNCATE``, que no es de ninguna regla
de facturación.

``search_path`` (S2-01): toda función del esquema fija
``pg_catalog, public, pg_temp`` (``pg_temp`` al final, explícito: si no, se
busca primero) y nombra sus tablas con el esquema. Una tabla temporal con el
nombre de una tabla de negocio no puede suplantarla dentro del trigger. Además
se retira ``TEMPORARY`` sobre la base de datos a ``PUBLIC`` y a
``kapataz_app`` (la migración falla si no lo consigue): la app no crea tablas
temporales.
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
    "invoices_insert_as_draft()",
    "invoices_check_issue()",
    "invoice_children_immutable_when_issued()",
    "invoice_reference_is_issued()",
    "series_counters_advance()",
    "series_counters_check_issued()",
    "billing_records_append_only()",
    "billing_records_check_link()",
    "billing_records_invoice_issued()",
    "billing_records_check_in_chain()",
    "billing_chain_heads_advance()",
    "reject_truncate_of_fiscal_table()",
    "invoice_series_number(text, integer, integer)",
)

# Cabecera común de las funciones de trigger (S2-01). Con pg_temp al final y
# las tablas con su esquema, una tabla temporal de la sesión no suplanta a una
# de negocio dentro del trigger.
_HEADER = "RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS"

# Ancho mínimo de la secuencia en el número de factura: _SEQUENCE_WIDTH de
# domain/billing/numbering.py. Con más cifras, el número no se recorta, igual
# que el formato de Python.
_SEQUENCE_WIDTH = 4

# Número de factura tal como lo escribe DocumentNumber.__str__ («F-2026-0001»).
# Lo usan los triggers para comprobar que un registro es de su factura.
_SERIES_NUMBER = f"""
CREATE FUNCTION public.invoice_series_number(series text, year integer, number integer)
RETURNS text LANGUAGE sql IMMUTABLE STRICT
SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT format('%s-%s-%s', series, year,
        lpad(number::text, greatest({_SEQUENCE_WIDTH}, length(number::text)), '0'))
$$
"""

# RN-F-02. Hoy todas las columnas de una factura son fiscales, así que cualquier
# cambio de una emitida se rechaza. Si un día se añade una que no lo sea (la
# ruta del PDF, por ejemplo), se resta aquí del to_jsonb.
_INVOICES_IMMUTABLE = f"""
CREATE FUNCTION public.invoices_immutable_when_issued() {_HEADER} $$
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

# RN-F-01. Una factura solo llega a emitida desde un borrador, por la emisión.
_INVOICES_INSERT_AS_DRAFT = f"""
CREATE FUNCTION public.invoices_insert_as_draft() {_HEADER} $$
BEGIN
    RAISE EXCEPTION 'RN-F-01: una factura nace en borrador; solo la emisión la numera.'
        USING ERRCODE = 'KZF01';
END;
$$
"""

# RN-F-01 y RN-F-07, al confirmar la transacción que emite. Es lo que hace
# IssueInvoice en una sola transacción: la factura toma el número siguiente
# del contador (que queda en ese número y esa fecha) y se encadena su registro
# de alta. Con una emisión por transacción, el contador acaba justo en ella.
_INVOICES_CHECK_ISSUE = f"""
CREATE FUNCTION public.invoices_check_issue() {_HEADER} $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.series_counters c
        WHERE c.tenant_id = NEW.tenant_id AND c.series = NEW.series
            AND c.year = NEW.issue_year AND c.last_number = NEW.number
            AND c.last_issue_date = NEW.issue_date
    ) THEN
        RAISE EXCEPTION 'RN-F-01: la factura se emite sin tomar su número del contador.'
            USING ERRCODE = 'KZF01';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.billing_records r
        WHERE r.tenant_id = NEW.tenant_id AND r.invoice_id = NEW.id
            AND r.record_type = 'registration' AND NOT r.is_correction
            AND r.issue_date = NEW.issue_date AND r.issuer_tax_id = NEW.issuer_tax_id
            AND r.series_number
                = public.invoice_series_number(NEW.series, NEW.issue_year, NEW.number)
    ) THEN
        RAISE EXCEPTION 'RN-F-07: la factura se emite sin su registro de alta.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NULL;
END;
$$
"""

# TG_ARGV[0] es la columna que apunta a la factura. FOR SHARE espera a una
# emisión en curso (que bloquea la factura con FOR UPDATE) y, a la vez, impide
# que la factura se emita mientras esta transacción cambia sus líneas.
_CHILDREN_IMMUTABLE = f"""
CREATE FUNCTION public.invoice_children_immutable_when_issued() {_HEADER} $$
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
        SELECT i.status FROM public.invoices i WHERE i.id = ANY (invoice_ids)
        ORDER BY i.id FOR SHARE
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

# La factura citada por una referencia fiscal tiene que estar emitida (y una
# emitida ya no vuelve a borrador). TG_ARGV[0] es la columna y TG_ARGV[1] la
# regla: RN-F-03 para la rectificada, RN-F-12 para la fase que se descuenta.
# Va AFTER: la clave foránea compuesta ya ha comprobado que la factura existe
# en la cuenta de la fila, así que no encontrarla es un error, no un permiso.
_REFERENCE_IS_ISSUED = f"""
CREATE FUNCTION public.invoice_reference_is_issued() {_HEADER} $$
DECLARE
    referenced uuid := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    referenced_status text;
BEGIN
    IF referenced IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT i.status INTO referenced_status FROM public.invoices i
        WHERE i.tenant_id = NEW.tenant_id AND i.id = referenced;
    IF referenced_status IS DISTINCT FROM 'issued' THEN
        RAISE EXCEPTION '%: % solo cita facturas emitidas.', TG_ARGV[1], TG_TABLE_NAME
            USING ERRCODE = 'KZF' || right(TG_ARGV[1], 2);
    END IF;
    RETURN NULL;
END;
$$
"""

# RN-F-01 y RN-F-04. El contador lo crea la emisión a cero (INSERT … ON
# CONFLICT DO NOTHING) y cada emisión lo sube en uno con su fecha.
_COUNTERS_ADVANCE = f"""
CREATE FUNCTION public.series_counters_advance() {_HEADER} $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.last_number <> 0 THEN
            RAISE EXCEPTION 'RN-F-01: un contador nace a cero.' USING ERRCODE = 'KZF01';
        END IF;
        RETURN NULL;
    END IF;
    IF (NEW.tenant_id, NEW.series, NEW.year) IS DISTINCT FROM (OLD.tenant_id, OLD.series, OLD.year)
    THEN
        RAISE EXCEPTION 'RN-F-01: un contador no cambia de cuenta, de serie ni de año.'
            USING ERRCODE = 'KZF01';
    END IF;
    IF (NEW.last_number, NEW.last_issue_date) IS NOT DISTINCT FROM
        (OLD.last_number, OLD.last_issue_date) THEN
        RETURN NULL;
    END IF;
    IF NEW.last_number IS DISTINCT FROM OLD.last_number + 1 THEN
        RAISE EXCEPTION 'RN-F-01: un contador solo avanza de uno en uno.'
            USING ERRCODE = 'KZF01';
    END IF;
    IF NEW.last_issue_date < OLD.last_issue_date THEN
        RAISE EXCEPTION 'RN-F-04: la fecha del último número no retrocede.'
            USING ERRCODE = 'KZF04';
    END IF;
    IF EXTRACT(YEAR FROM NEW.last_issue_date) <> NEW.year THEN
        RAISE EXCEPTION 'RN-F-01: la fecha del último número es de otro año.'
            USING ERRCODE = 'KZF01';
    END IF;
    RETURN NULL;
END;
$$
"""

# RN-F-01, al confirmar: cada número que da el contador es el de una factura
# emitida en esa serie, ese año y esa fecha. Sin ella, quedaría un hueco.
_COUNTERS_CHECK_ISSUED = f"""
CREATE FUNCTION public.series_counters_check_issued() {_HEADER} $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.invoices i
        WHERE i.tenant_id = NEW.tenant_id AND i.series = NEW.series
            AND i.issue_year = NEW.year AND i.number = NEW.last_number
            AND i.issue_date = NEW.last_issue_date AND i.status = 'issued'
    ) THEN
        RAISE EXCEPTION 'RN-F-01: el contador avanza sin la factura emitida de ese número.'
            USING ERRCODE = 'KZF01';
    END IF;
    RETURN NULL;
END;
$$
"""

_RECORDS_APPEND_ONLY = f"""
CREATE FUNCTION public.billing_records_append_only() {_HEADER} $$
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
_RECORDS_CHECK_LINK = f"""
CREATE FUNCTION public.billing_records_check_link() {_HEADER} $$
DECLARE
    previous public.billing_records%ROWTYPE;
BEGIN
    IF NEW.previous_record_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO previous FROM public.billing_records r
        WHERE r.tenant_id = NEW.tenant_id AND r.id = NEW.previous_record_id;
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

# RN-F-07. Un registro (alta, subsanación o anulación) es siempre de una
# factura emitida y la identifica tal cual: emisor, número y fecha de esa
# factura (IDFactura de la AEAT). AFTER, por lo mismo que las referencias
# fiscales. La huella no se comprueba aquí: la calcula el dominio.
_RECORDS_INVOICE_ISSUED = f"""
CREATE FUNCTION public.billing_records_invoice_issued() {_HEADER} $$
DECLARE
    invoice public.invoices%ROWTYPE;
BEGIN
    SELECT * INTO invoice FROM public.invoices i
        WHERE i.tenant_id = NEW.tenant_id AND i.id = NEW.invoice_id;
    IF NOT FOUND OR invoice.status IS DISTINCT FROM 'issued' THEN
        RAISE EXCEPTION 'RN-F-07: un registro de facturación es de una factura emitida.'
            USING ERRCODE = 'KZF07';
    END IF;
    IF NEW.issuer_tax_id IS DISTINCT FROM invoice.issuer_tax_id
        OR NEW.issue_date IS DISTINCT FROM invoice.issue_date
        OR NEW.series_number IS DISTINCT FROM
            public.invoice_series_number(invoice.series, invoice.issue_year, invoice.number)
    THEN
        RAISE EXCEPTION 'RN-F-07: el registro no identifica a su factura (emisor, número y fecha).'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NULL;
END;
$$
"""

# RN-F-07, al confirmar: el registro entra en la cadena. La cabeza ha llegado a
# él o lo ha pasado (otro registro lo enlaza). Un registro suelto bloquearía la
# cadena: el siguiente no podría enlazar con el anterior sin bifurcarla.
_RECORDS_CHECK_IN_CHAIN = f"""
CREATE FUNCTION public.billing_records_check_in_chain() {_HEADER} $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.billing_chain_heads h
        WHERE h.tenant_id = NEW.tenant_id AND h.last_record_id = NEW.id
    ) AND NOT EXISTS (
        SELECT 1 FROM public.billing_records r
        WHERE r.tenant_id = NEW.tenant_id AND r.previous_record_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'RN-F-07: la cabeza de la cadena no llega al registro.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NULL;
END;
$$
"""

_HEADS_ADVANCE = f"""
CREATE FUNCTION public.billing_chain_heads_advance() {_HEADER} $$
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
    SELECT r.previous_record_id INTO linked_to FROM public.billing_records r
        WHERE r.tenant_id = NEW.tenant_id AND r.id = NEW.last_record_id;
    IF NOT FOUND OR linked_to IS DISTINCT FROM OLD.last_record_id THEN
        RAISE EXCEPTION 'RN-F-07: la cabeza solo avanza al registro siguiente.'
            USING ERRCODE = 'KZF07';
    END IF;
    RETURN NEW;
END;
$$
"""

# Vaciar una tabla no es ninguna operación de facturación: código propio
# (KZF00), distinto del de la factura emitida inmutable (M-10).
_REJECT_TRUNCATE = f"""
CREATE FUNCTION public.reject_truncate_of_fiscal_table() {_HEADER} $$
BEGIN
    RAISE EXCEPTION 'La tabla % no se vacía: TRUNCATE no está permitido.', TG_TABLE_NAME
        USING ERRCODE = 'KZF00';
END;
$$
"""

# Todas las funciones: se crean antes que los triggers que las usan.
_FUNCTION_DEFINITIONS = (
    _SERIES_NUMBER,
    _INVOICES_IMMUTABLE,
    _INVOICES_INSERT_AS_DRAFT,
    _INVOICES_CHECK_ISSUE,
    _CHILDREN_IMMUTABLE,
    _REFERENCE_IS_ISSUED,
    _COUNTERS_ADVANCE,
    _COUNTERS_CHECK_ISSUED,
    _RECORDS_APPEND_ONLY,
    _RECORDS_CHECK_LINK,
    _RECORDS_INVOICE_ISSUED,
    _RECORDS_CHECK_IN_CHAIN,
    _HEADS_ADVANCE,
    _REJECT_TRUNCATE,
)

# Los triggers diferidos se comprueban al confirmar la transacción: la
# emisión cambia la factura, el contador, la cadena y la cabeza en ese orden y
# solo al final cuadra todo.
_DEFERRED = "DEFERRABLE INITIALLY DEFERRED"

_TRIGGERS = (
    (
        "CREATE TRIGGER invoices_immutable_when_issued "
        "BEFORE UPDATE OR DELETE ON public.invoices "
        "FOR EACH ROW EXECUTE FUNCTION public.invoices_immutable_when_issued()"
    ),
    (
        "CREATE TRIGGER invoices_insert_as_draft "
        "AFTER INSERT ON public.invoices "
        "FOR EACH ROW WHEN (NEW.status IS DISTINCT FROM 'draft') "
        "EXECUTE FUNCTION public.invoices_insert_as_draft()"
    ),
    (
        f"CREATE CONSTRAINT TRIGGER invoices_check_issue "
        f"AFTER UPDATE ON public.invoices {_DEFERRED} "
        f"FOR EACH ROW WHEN (OLD.status = 'draft' AND NEW.status = 'issued') "
        f"EXECUTE FUNCTION public.invoices_check_issue()"
    ),
    (
        "CREATE TRIGGER invoice_lines_immutable_when_issued "
        "BEFORE INSERT OR UPDATE OR DELETE ON public.invoice_lines "
        "FOR EACH ROW EXECUTE FUNCTION public.invoice_children_immutable_when_issued('invoice_id')"
    ),
    (
        "CREATE TRIGGER invoice_lines_prior_invoice_issued "
        "AFTER INSERT OR UPDATE OF prior_invoice_id ON public.invoice_lines "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.invoice_reference_is_issued('prior_invoice_id', 'RN-F-12')"
    ),
    (
        "CREATE TRIGGER invoice_corrections_immutable_when_issued "
        "BEFORE INSERT OR UPDATE OR DELETE ON public.invoice_corrections "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.invoice_children_immutable_when_issued('corrective_invoice_id')"
    ),
    (
        "CREATE TRIGGER invoice_corrections_rectified_issued "
        "AFTER INSERT OR UPDATE OF rectified_invoice_id ON public.invoice_corrections "
        "FOR EACH ROW EXECUTE FUNCTION "
        "public.invoice_reference_is_issued('rectified_invoice_id', 'RN-F-03')"
    ),
    (
        "CREATE TRIGGER series_counters_advance "
        "AFTER INSERT OR UPDATE ON public.series_counters "
        "FOR EACH ROW EXECUTE FUNCTION public.series_counters_advance()"
    ),
    (
        f"CREATE CONSTRAINT TRIGGER series_counters_check_issued "
        f"AFTER UPDATE ON public.series_counters {_DEFERRED} "
        f"FOR EACH ROW WHEN (NEW.last_number IS DISTINCT FROM OLD.last_number) "
        f"EXECUTE FUNCTION public.series_counters_check_issued()"
    ),
    (
        "CREATE TRIGGER billing_records_append_only "
        "BEFORE UPDATE OR DELETE ON public.billing_records "
        "FOR EACH ROW EXECUTE FUNCTION public.billing_records_append_only()"
    ),
    (
        "CREATE TRIGGER billing_records_check_link "
        "BEFORE INSERT ON public.billing_records "
        "FOR EACH ROW EXECUTE FUNCTION public.billing_records_check_link()"
    ),
    (
        "CREATE TRIGGER billing_records_invoice_issued "
        "AFTER INSERT ON public.billing_records "
        "FOR EACH ROW EXECUTE FUNCTION public.billing_records_invoice_issued()"
    ),
    (
        f"CREATE CONSTRAINT TRIGGER billing_records_check_in_chain "
        f"AFTER INSERT ON public.billing_records {_DEFERRED} "
        f"FOR EACH ROW EXECUTE FUNCTION public.billing_records_check_in_chain()"
    ),
    (
        "CREATE TRIGGER billing_chain_heads_advance "
        "BEFORE INSERT OR UPDATE ON public.billing_chain_heads "
        "FOR EACH ROW EXECUTE FUNCTION public.billing_chain_heads_advance()"
    ),
    *(
        f"CREATE TRIGGER {table}_reject_truncate BEFORE TRUNCATE ON public.{table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.reject_truncate_of_fiscal_table()"
        for table in _NO_TRUNCATE_TABLES
    ),
)

# S2-01. Sin TEMPORARY, la app no crea tablas temporales que puedan hacerse
# pasar por las de negocio. Las bases nuevas lo conceden a PUBLIC por defecto
# (la base de pruebas, por ejemplo); 10-roles.sh ya no se lo da a kapataz_app,
# y aquí se retira en cualquier caso: lo que concede un superusuario consta
# como concedido por el propietario de la base de datos, que es quien migra.
# El propietario lo conserva; no es un rol que use la app.
_REVOKE_TEMPORARY = f"""
DO $$
BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC, {APP_ROLE}', current_database());
    -- REVOKE solo avisa (WARNING) si quien migra no puede retirarlo: aquí falla.
    IF has_database_privilege('public', current_database(), 'TEMPORARY')
        OR has_database_privilege('{APP_ROLE}', current_database(), 'TEMPORARY') THEN
        RAISE EXCEPTION 'S2-01: PUBLIC o {APP_ROLE} siguen pudiendo crear tablas temporales.';
    END IF;
END
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
            "(status = 'draft' AND (quote_version_id IS NULL "
            "OR (recipient_type IS NULL AND dwelling_over_two_years IS NULL))) "
            "OR (status = 'issued' AND recipient_type IS NOT NULL "
            "AND (recipient_type = 'business' OR dwelling_over_two_years IS NOT NULL))",
            name=op.f("ck_invoices_works_recipient"),
        ),
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
    # RN-F-07: un solo alta por factura; las demás altas son subsanaciones.
    op.create_index(
        "uq_billing_records_registration",
        "billing_records",
        ["tenant_id", "invoice_id"],
        unique=True,
        postgresql_where=sa.text("record_type = 'registration' AND NOT is_correction"),
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
    for function in _FUNCTION_DEFINITIONS:
        op.execute(function)
    for trigger in _TRIGGERS:
        op.execute(trigger)
    op.execute(_REVOKE_TEMPORARY)


def downgrade() -> None:
    # Al borrar las tablas se van con ellas sus políticas y sus triggers; las
    # funciones se borran después. Los permisos se retiran antes, como en 0001.
    # TEMPORARY no se devuelve a PUBLIC ni a la app: es un endurecimiento de la
    # base de datos, no de estas tablas, y devolverlo reabriría S2-01.
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
    op.drop_index("uq_billing_records_registration", table_name="billing_records")
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
        op.execute(f"DROP FUNCTION IF EXISTS public.{function}")
