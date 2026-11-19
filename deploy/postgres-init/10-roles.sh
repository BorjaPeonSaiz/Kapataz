#!/bin/sh
# Crea los roles de Kapataz en una base de datos recién inicializada
# (arquitectura §5.4, ADR-024).
#
# - kapataz_owner: propietario de la base de datos y del esquema public.
#   Ejecuta las migraciones (DATABASE_MIGRATION_URL).
# - kapataz_app: rol de la aplicación (DATABASE_URL). Sin BYPASSRLS, sin
#   propiedad de tablas y sin permiso para crear objetos. Aquí solo recibe
#   CONNECT y USAGE sobre el esquema: los permisos sobre cada tabla los da
#   su migración, tabla a tabla (mínimo privilegio, ADR-024).
#
# La imagen de PostgreSQL lo ejecuta una sola vez, al crear el volumen de
# datos. También se puede lanzar a mano contra un servidor vacío (lo hace el
# CI): usa las variables PG* de libpq para conectarse.
#
# Variables:
#   POSTGRES_USER                superusuario (por defecto, postgres)
#   POSTGRES_DB                  base de datos de Kapataz (por defecto, kapataz)
#   KAPATAZ_OWNER_DB_PASSWORD    contraseña de kapataz_owner
#   KAPATAZ_APP_DB_PASSWORD      contraseña de kapataz_app
#
# Las contraseñas pasan a psql como variables y se citan con :'var', así que
# no hace falta escaparlas.
#
# Todo va en un subshell: si el fichero no tiene permiso de ejecución, la
# imagen de PostgreSQL lo carga con «source», y así no altera las opciones de
# su entrypoint. Un error dentro del subshell sigue parando la inicialización.

(
set -eu

: "${KAPATAZ_OWNER_DB_PASSWORD:?Falta KAPATAZ_OWNER_DB_PASSWORD}"
: "${KAPATAZ_APP_DB_PASSWORD:?Falta KAPATAZ_APP_DB_PASSWORD}"

kapataz_db=${POSTGRES_DB:-kapataz}
kapataz_superuser=${POSTGRES_USER:-postgres}

psql --no-psqlrc --set=ON_ERROR_STOP=1 \
    --username "$kapataz_superuser" \
    --dbname "$kapataz_db" \
    --set=db_name="$kapataz_db" \
    --set=owner_password="$KAPATAZ_OWNER_DB_PASSWORD" \
    --set=app_password="$KAPATAZ_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE kapataz_owner
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'owner_password';

CREATE ROLE kapataz_app
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'app_password';

-- pgvector necesita superusuario para instalarse; las migraciones solo
-- comprueban que existe (CREATE EXTENSION IF NOT EXISTS).
CREATE EXTENSION IF NOT EXISTS vector;

ALTER DATABASE :"db_name" OWNER TO kapataz_owner;
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
-- Sin TEMPORARY: una tabla temporal con el nombre de una tabla de negocio
-- podría suplantarla en una consulta sin esquema (S2-01). La app no usa
-- tablas temporales; la migración 0003 lo retira también en bases creadas
-- de otra forma.
GRANT CONNECT ON DATABASE :"db_name" TO kapataz_app;

-- Solo kapataz_owner crea objetos en public.
ALTER SCHEMA public OWNER TO kapataz_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO kapataz_app;

-- Sin ALTER DEFAULT PRIVILEGES: cada migración concede a kapataz_app solo
-- lo que necesita sobre sus tablas y secuencias (ADR-024). Así
-- alembic_version y las tablas de solo inserción no reciben UPDATE ni DELETE.
SQL
)
