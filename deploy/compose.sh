#!/bin/sh
# docker compose de producción con la etiqueta que está en marcha.
#
#   sh deploy/compose.sh ps
#   sh deploy/compose.sh logs --tail=200 kapataz
#   sh deploy/compose.sh run --rm kapataz-tools kapataz-admin create-user --email ...
#
# Toma la etiqueta de .deploy/current, salvo que se pase KAPATAZ_IMAGE_TAG.
# Para desplegar o volver atrás no se usa: deploy.sh y rollback.sh.

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

if [ -z "${KAPATAZ_IMAGE_TAG:-}" ]; then
    KAPATAZ_IMAGE_TAG=$(kapataz_state_get current)
    [ -n "$KAPATAZ_IMAGE_TAG" ] \
        || kapataz_die "no hay despliegue en $KAPATAZ_STATE_DIR/current; usa deploy/deploy.sh"
fi
export KAPATAZ_IMAGE_TAG

kapataz_compose "$@"
