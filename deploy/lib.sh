# shellcheck shell=sh
# Funciones comunes de los scripts de deploy/. No se ejecuta: se carga con
#   . "$KAPATAZ_ROOT/deploy/lib.sh"
# después de fijar KAPATAZ_ROOT (la raíz del repositorio; en el servidor,
# /opt/kapataz).
#
# Estado del despliegue (fuera de git, en .deploy/):
#   current   etiqueta de la imagen que está en marcha
#   previous  etiqueta anterior, a la que vuelve rollback.sh
#   history   registro de despliegues y vueltas atrás

: "${KAPATAZ_ROOT:?Falta KAPATAZ_ROOT}"
KAPATAZ_STATE_DIR=${KAPATAZ_STATE_DIR:-$KAPATAZ_ROOT/.deploy}
# Tiempo máximo para que los servicios queden sanos tras «up».
KAPATAZ_WAIT_TIMEOUT=${KAPATAZ_WAIT_TIMEOUT:-180}

kapataz_log() {
    printf '%s [kapataz] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

kapataz_die() {
    kapataz_log "ERROR: $*"
    exit 1
}

kapataz_require() {
    for kapataz_cmd in "$@"; do
        command -v "$kapataz_cmd" >/dev/null 2>&1 \
            || kapataz_die "falta la orden «$kapataz_cmd»"
    done
}

# docker compose con el fichero de producción, el proyecto kapataz y la
# etiqueta que se le pase en KAPATAZ_IMAGE_TAG.
kapataz_compose() {
    docker compose \
        --project-directory "$KAPATAZ_ROOT" \
        --file "$KAPATAZ_ROOT/docker-compose.yml" \
        "$@"
}

kapataz_state_get() {
    if [ -r "$KAPATAZ_STATE_DIR/$1" ]; then
        sed -n '1p' "$KAPATAZ_STATE_DIR/$1"
    fi
}

kapataz_state_set() {
    mkdir -p "$KAPATAZ_STATE_DIR"
    printf '%s\n' "$2" >"$KAPATAZ_STATE_DIR/$1.tmp"
    mv "$KAPATAZ_STATE_DIR/$1.tmp" "$KAPATAZ_STATE_DIR/$1"
}

kapataz_history() {
    mkdir -p "$KAPATAZ_STATE_DIR"
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >>"$KAPATAZ_STATE_DIR/history"
}

# Commit de git que corresponde a una etiqueta de imagen: el propio commit
# hasta la 1.0.0 (ADR-032) o la etiqueta vX.Y.Z desde entonces.
kapataz_tag_commit() {
    git -C "$KAPATAZ_ROOT" rev-parse --verify --quiet "$1^{commit}" \
        || git -C "$KAPATAZ_ROOT" rev-parse --verify --quiet "v$1^{commit}"
}

kapataz_db_running() {
    [ -n "$(KAPATAZ_IMAGE_TAG=unused kapataz_compose ps --status running --quiet kapataz-db 2>/dev/null)" ]
}

# Comprueba /api/health como lo vería el nginx de KronoQR: desde la red
# kronoqr-app, por el nombre kapataz. Exige además que ese nombre resuelva a
# un solo contenedor (ADR-014, «Prueba de red») y que la versión que informa
# /api/health sea la etiqueta desplegada (el commit hasta la 1.0.0, ADR-032).
kapataz_check_health() {
    docker run --rm \
        --network kronoqr-app \
        --read-only --cap-drop ALL --security-opt no-new-privileges:true \
        --env "KAPATAZ_EXPECTED_VERSION=$1" \
        --entrypoint python \
        "kapataz:$1" -c '
import json, os, socket, sys, urllib.request
ips = {info[4][0] for info in socket.getaddrinfo("kapataz", 8000, proto=socket.IPPROTO_TCP)}
if len(ips) != 1:
    sys.exit("kapataz resuelve a %d direcciones en kronoqr-app: %s" % (len(ips), sorted(ips)))
with urllib.request.urlopen("http://kapataz:8000/api/health", timeout=5) as r:
    body = r.read().decode("utf-8", "replace")
print("health %s" % body[:500])
version = json.loads(body).get("version")
expected = os.environ["KAPATAZ_EXPECTED_VERSION"]
if version != expected:
    sys.exit("/api/health informa la versión %r y se esperaba %r" % (version, expected))
'
}

# Pone en marcha la api y el worker con la etiqueta dada y espera a que estén
# sanos. No toca la base de datos ni ejecuta migraciones.
kapataz_activate() {
    kapataz_log "arrancando kapataz y kapataz-worker con kapataz:$1"
    KAPATAZ_IMAGE_TAG=$1 kapataz_compose up --detach --no-build \
        --wait --wait-timeout "$KAPATAZ_WAIT_TIMEOUT" \
        kapataz kapataz-worker \
        && kapataz_check_health "$1"
}

# Deja el árbol de trabajo en el commit de una etiqueta, para que
# docker-compose.yml y deploy/postgres-init coincidan con la imagen.
kapataz_checkout() {
    git -C "$KAPATAZ_ROOT" -c advice.detachedHead=false checkout --quiet --detach "$1"
}
