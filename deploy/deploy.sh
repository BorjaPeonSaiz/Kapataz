#!/bin/sh
# Despliega en el servidor la imagen de un commit de main (ADR-014).
#
#   sh deploy/deploy.sh <commit>
#
# Pasos:
#   1. Construye kapataz:<commit> en el servidor desde «git archive» (solo lo
#      versionado entra en el contexto; nunca .env).
#   2. Deja /opt/kapataz en ese commit (docker-compose.yml y postgres-init).
#   3. Copia cifrada de la base de datos (deploy/backup-db.sh), si ya existe.
#   4. Migraciones con alembic upgrade head (servicio kapataz-tools).
#   5. up -d de kapataz y kapataz-worker y espera a que estén sanos.
#   6. Comprueba /api/health desde la red kronoqr-app.
# Si falla algo a partir del paso 2, vuelve al commit y a la etiqueta
# anteriores. La versión anterior no se para hasta el paso 5, así que un
# fallo en la construcción, la copia o las migraciones no la interrumpe.
#
# Las migraciones no se deshacen solas: deben ser compatibles con la versión
# anterior (dos pasos si no son reversibles). Si una migración rompe datos, se
# restaura la copia del paso 3 (docs/operacion/despliegue.md).
#
# Variables opcionales:
#   KAPATAZ_ALLOW_NON_MAIN=1   permite un commit que no está en origin/main
#   KAPATAZ_SKIP_BACKUP=1      omite la copia (solo sin datos reales: registro cerrado, RN-13)
#   KAPATAZ_WAIT_TIMEOUT=180   segundos de espera de los health checks

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

usage() {
    printf 'Uso: %s <commit>\n' "$0" >&2
    exit 2
}

# Vuelve a lo que había antes del despliegue. Se llama solo si ya se ha
# cambiado el árbol de trabajo.
restore_previous() {
    kapataz_log "volviendo al commit $previous_commit"
    kapataz_checkout "$previous_commit" || kapataz_log "no se pudo volver al commit $previous_commit"
    if [ -n "$previous_tag" ]; then
        if kapataz_activate "$previous_tag"; then
            kapataz_history "deploy-fallido $commit; sigue $previous_tag"
            kapataz_log "la versión anterior (kapataz:$previous_tag) sigue funcionando"
        else
            kapataz_history "deploy-fallido $commit; la vuelta a $previous_tag también falla"
            kapataz_log "ATENCIÓN: la vuelta a kapataz:$previous_tag también ha fallado"
        fi
    else
        kapataz_history "deploy-fallido $commit; no había versión anterior"
        kapataz_log "no había versión anterior a la que volver"
    fi
}

main() {
    [ "$#" -eq 1 ] || usage
    kapataz_require docker git

    cd "$KAPATAZ_ROOT"
    [ -r "$KAPATAZ_ROOT/.env" ] || kapataz_die "falta $KAPATAZ_ROOT/.env"

    git fetch --quiet --tags origin
    commit=$(git rev-parse --verify --quiet "$1^{commit}") \
        || kapataz_die "«$1» no es un commit conocido (¿falta git fetch?)"
    if [ "${KAPATAZ_ALLOW_NON_MAIN:-0}" != 1 ] \
        && ! git merge-base --is-ancestor "$commit" origin/main; then
        kapataz_die "$commit no está en origin/main; solo se despliega lo integrado"
    fi
    if ! git diff --quiet || ! git diff --cached --quiet; then
        kapataz_die "el árbol de trabajo de $KAPATAZ_ROOT tiene cambios sin versionar"
    fi

    previous_tag=$(kapataz_state_get current)
    previous_commit=$(git rev-parse HEAD)
    kapataz_log "desplegando $commit (en marcha: ${previous_tag:-ninguna})"

    # 1. Imagen
    if docker image inspect "kapataz:$commit" >/dev/null 2>&1; then
        kapataz_log "kapataz:$commit ya existe; no se reconstruye"
    else
        build_dir=$(mktemp -d)
        trap 'rm -rf "$build_dir"' EXIT
        git archive --format=tar --output="$build_dir/context.tar" "$commit"
        kapataz_log "construyendo kapataz:$commit"
        docker build \
            --build-arg "GIT_COMMIT=$commit" \
            --tag "kapataz:$commit" \
            - <"$build_dir/context.tar"
        rm -rf "$build_dir"
        trap - EXIT
    fi

    # 2. Árbol de trabajo
    kapataz_checkout "$commit"

    # 3. Copia de la base de datos
    if kapataz_db_running; then
        if [ "${KAPATAZ_SKIP_BACKUP:-0}" = 1 ]; then
            kapataz_log "AVISO: copia omitida por KAPATAZ_SKIP_BACKUP=1"
        elif ! sh "$KAPATAZ_ROOT/deploy/backup-db.sh" "pre-deploy-$commit"; then
            kapataz_log "la copia ha fallado; no se despliega"
            restore_previous
            exit 1
        fi
    else
        kapataz_log "kapataz-db no está en marcha (primer despliegue): sin copia"
    fi

    # 4. Base de datos y migraciones
    if ! KAPATAZ_IMAGE_TAG=$commit kapataz_compose up --detach --no-build \
        --wait --wait-timeout "$KAPATAZ_WAIT_TIMEOUT" kapataz-db; then
        kapataz_log "kapataz-db no queda sana"
        restore_previous
        exit 1
    fi
    kapataz_log "aplicando migraciones"
    if ! KAPATAZ_IMAGE_TAG=$commit kapataz_compose run --rm --no-deps kapataz-tools; then
        kapataz_log "las migraciones han fallado"
        restore_previous
        exit 1
    fi

    # 5 y 6. Nueva versión
    if ! kapataz_activate "$commit"; then
        kapataz_log "kapataz:$commit no pasa el health check"
        restore_previous
        exit 1
    fi

    if [ -n "$previous_tag" ] && [ "$previous_tag" != "$commit" ]; then
        kapataz_state_set previous "$previous_tag"
    fi
    kapataz_state_set current "$commit"
    kapataz_history "deploy $commit (anterior: ${previous_tag:-ninguna})"
    kapataz_log "desplegado kapataz:$commit"
    kapataz_log "falta comprobar HTTPS, HSTS, SSE e IP real (docs/operacion/despliegue.md)"
}

# Todo dentro de main: el checkout del paso 2 puede cambiar este fichero
# mientras se ejecuta, y así el shell ya lo ha leído entero.
main "$@"
exit 0
