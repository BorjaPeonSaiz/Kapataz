#!/bin/sh
# Vuelve a una etiqueta anterior de la imagen (ADR-014).
#
#   sh deploy/rollback.sh            vuelve a la etiqueta de .deploy/previous
#   sh deploy/rollback.sh <etiqueta> vuelve a esa etiqueta (debe existir la imagen)
#
# Recrea solo kapataz y kapataz-worker; la base de datos sigue en marcha y no
# se deshace ninguna migración. Por eso cada migración tiene que ser
# compatible con la versión anterior. Si hay que deshacer datos, se restaura
# una copia (docs/operacion/despliegue.md, «Restaurar una copia»).

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

main() {
    [ "$#" -le 1 ] || {
        printf 'Uso: %s [etiqueta]\n' "$0" >&2
        exit 2
    }
    kapataz_require docker git
    cd "$KAPATAZ_ROOT"

    current_tag=$(kapataz_state_get current)
    target_tag=${1:-$(kapataz_state_get previous)}
    [ -n "$target_tag" ] || kapataz_die "no hay etiqueta anterior en $KAPATAZ_STATE_DIR/previous; indica una"
    [ "$target_tag" != "$current_tag" ] || kapataz_die "kapataz:$target_tag ya es la versión en marcha"

    docker image inspect "kapataz:$target_tag" >/dev/null 2>&1 \
        || kapataz_die "no existe la imagen kapataz:$target_tag en este servidor"
    target_commit=$(kapataz_tag_commit "$target_tag") \
        || kapataz_die "no encuentro en git el commit de la etiqueta $target_tag"

    previous_commit=$(git rev-parse HEAD)
    kapataz_log "vuelta atrás: ${current_tag:-ninguna} -> $target_tag"
    kapataz_checkout "$target_commit"

    if kapataz_activate "$target_tag"; then
        [ -z "$current_tag" ] || kapataz_state_set previous "$current_tag"
        kapataz_state_set current "$target_tag"
        kapataz_history "rollback $target_tag (antes: ${current_tag:-ninguna})"
        kapataz_log "en marcha kapataz:$target_tag"
        return 0
    fi

    kapataz_log "kapataz:$target_tag no pasa el health check"
    kapataz_checkout "$previous_commit" || true
    if [ -n "$current_tag" ] && kapataz_activate "$current_tag"; then
        kapataz_history "rollback-fallido $target_tag; sigue $current_tag"
        kapataz_log "se mantiene kapataz:$current_tag"
    else
        kapataz_history "rollback-fallido $target_tag; sin versión sana"
        kapataz_log "ATENCIÓN: no queda ninguna versión sana en marcha"
    fi
    exit 1
}

main "$@"
exit 0
