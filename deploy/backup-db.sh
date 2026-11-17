#!/bin/sh
# Copia cifrada de la base de datos de Kapataz (RNF-15).
#
#   sh deploy/backup-db.sh [etiqueta]
#
# Hace pg_dump en formato custom dentro de kapataz-db y lo cifra con age
# hacia la clave pública de BACKUP_AGE_RECIPIENTS_FILE. En el servidor solo
# está la clave pública: quien tenga acceso al servidor no puede leer las
# copias. La clave privada se guarda fuera del servidor.
#
# Resultado: $BACKUP_DIR/kapataz-<fecha UTC>-<etiqueta>.dump.age (permisos 600).
#
# Pendiente del Bloque 10 (ADR-014, RNF-15): enviar cada copia fuera del
# servidor, a un almacenamiento en la UE, y el archivado continuo de WAL para
# RPO <= 15 min. Hasta entonces la copia se queda en este servidor y no
# protege de su pérdida.
#
# Variables opcionales:
#   BACKUP_DIR                 por defecto /var/backups/kapataz
#   BACKUP_AGE_RECIPIENTS_FILE por defecto $KAPATAZ_ROOT/.deploy/backup-recipients.txt
#   BACKUP_RETENTION_DAYS      por defecto 14; las copias más antiguas se borran

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

BACKUP_DIR=${BACKUP_DIR:-/var/backups/kapataz}
BACKUP_AGE_RECIPIENTS_FILE=${BACKUP_AGE_RECIPIENTS_FILE:-$KAPATAZ_STATE_DIR/backup-recipients.txt}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}

main() {
    [ "$#" -le 1 ] || {
        printf 'Uso: %s [etiqueta]\n' "$0" >&2
        exit 2
    }
    label=$(printf '%s' "${1:-manual}" | tr -c 'A-Za-z0-9._-' '_')
    kapataz_require docker age

    [ -s "$BACKUP_AGE_RECIPIENTS_FILE" ] \
        || kapataz_die "falta la clave pública de age en $BACKUP_AGE_RECIPIENTS_FILE"
    kapataz_db_running || kapataz_die "kapataz-db no está en marcha"

    umask 077
    mkdir -p "$BACKUP_DIR"
    stamp=$(date -u '+%Y%m%dT%H%M%SZ')
    target="$BACKUP_DIR/kapataz-$stamp-$label.dump.age"
    partial="$target.partial"
    status_file=$(mktemp)
    trap 'rm -f "$partial" "$status_file"' EXIT

    kapataz_log "copia de la base de datos en $target"
    # POSIX sh no tiene pipefail: el estado de pg_dump se guarda aparte.
    {
        dump_rc=0
        KAPATAZ_IMAGE_TAG=unused kapataz_compose exec -T kapataz-db \
            pg_dump --username=postgres --dbname=kapataz \
            --format=custom --compress=6 --no-password || dump_rc=$?
        printf '%s\n' "$dump_rc" >"$status_file"
    } | age --encrypt --recipients-file "$BACKUP_AGE_RECIPIENTS_FILE" --output "$partial"

    dump_status=$(cat "$status_file")
    [ "$dump_status" = 0 ] || kapataz_die "pg_dump ha terminado con el código $dump_status"
    [ -s "$partial" ] || kapataz_die "la copia está vacía"

    mv "$partial" "$target"
    trap - EXIT
    rm -f "$status_file"
    kapataz_log "copia hecha ($(wc -c <"$target" | tr -d ' ') bytes)"

    # Retención local. Una copia que no se ha restaurado no cuenta como copia:
    # el simulacro de restauración está en docs/operacion/despliegue.md.
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'kapataz-*.dump.age' \
        -mtime +"$BACKUP_RETENTION_DAYS" -exec rm -f {} +
}

main "$@"
exit 0
