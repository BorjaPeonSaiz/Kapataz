#!/bin/sh
# Levanta Kapataz en local con el mismo Compose que producción más
# docker-compose.local.yml (ADR-014: cada cambio se prueba en local antes de
# desplegarlo).
#
#   cp .env.local.example .env.local   # la primera vez
#   sh deploy/local-up.sh              # http://localhost:8000
#   sh deploy/local-up.sh --https 192.168.1.50
#                                      # https://192.168.1.50:8443, también
#                                      # desde el móvil en la misma red
#
# - Crea la red kronoqr-app si no existe. En local está vacía o es la del
#   entorno de desarrollo de KronoQR: solo se une a ella, nunca la toca.
# - Construye la imagen kapataz:$KAPATAZ_IMAGE_TAG (por defecto, «local»),
#   arranca la base de datos, aplica las migraciones y arranca la api y el
#   worker, esperando a sus health checks.
#
# Modo HTTPS (docs/operacion/https-local.md):
# - La IP es la del portátil en la red local; el script no la adivina. Solo
#   se admiten direcciones privadas (10/8, 172.16/12 y 192.168/16).
# - Genera con mkcert, en .local-tls/ (fuera de git y de la imagen), un
#   certificado para esa IP, localhost y 127.0.0.1. Lo regenera si cambia la
#   IP o la autoridad de mkcert. No instala mkcert ni ejecuta mkcert -install.
# - Arranca la app con COOKIE_SECURE=true, PUBLIC_BASE_URL=https://<IP>:8443
#   y FORWARDED_ALLOW_IPS limitado a la subred real de kronoqr-app, y el
#   proxy kapataz-local-tls (nginx sin root) con la configuración de
#   producción, publicado solo en 127.0.0.1 y en esa IP.
# - Sin --https, si el proxy estaba en marcha, lo para: la app vuelve al modo
#   HTTP y el proxy le pasaría cabeceras que ya no acepta.
#
# Variables opcionales:
#   KAPATAZ_LOCAL_ENV_FILE   por defecto .env.local
#   KAPATAZ_SKIP_BUILD=1     usa una imagen ya construida (la usa el CI)

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

local_env_file=${KAPATAZ_LOCAL_ENV_FILE:-$KAPATAZ_ROOT/.env.local}
tls_dir=$KAPATAZ_ROOT/.local-tls
tls_port=8443
tls_container=kapataz-local-tls

local_compose() {
    docker compose \
        --project-directory "$KAPATAZ_ROOT" \
        --env-file "$local_env_file" \
        --file "$KAPATAZ_ROOT/docker-compose.yml" \
        --file "$KAPATAZ_ROOT/docker-compose.local.yml" \
        "$@"
}

usage() {
    cat <<'EOF'
Uso: sh deploy/local-up.sh [--https <IP del portátil en la red local>]

Sin opciones: http://localhost:8000, solo en este portátil.
Con --https: https://<IP>:8443 desde el portátil y desde el móvil en la
misma red. Necesita mkcert (docs/operacion/https-local.md).
EOF
}

# 0 si $1 es una IPv4 privada (RFC 1918) escrita sin ceros a la izquierda.
is_private_ipv4() {
    case $1 in
        '' | *[!0-9.]* | .* | *. | *..*) return 1 ;;
    esac
    # Separa los cuatro octetos; $1 ya solo tiene dígitos y puntos.
    old_ifs=$IFS
    IFS=.
    # shellcheck disable=SC2086 # división en octetos intencionada
    set -- $1
    IFS=$old_ifs
    [ "$#" -eq 4 ] || return 1
    for octet in "$@"; do
        case $octet in
            0?*) return 1 ;;
        esac
        [ "${#octet}" -le 3 ] && [ "$octet" -le 255 ] || return 1
    done
    case $1 in
        10) return 0 ;;
        172) [ "$2" -ge 16 ] && [ "$2" -le 31 ] ;;
        192) [ "$2" -eq 168 ] ;;
        *) return 1 ;;
    esac
}

mkcert_missing() {
    kapataz_die "falta mkcert, necesario para --https. En Windows (PowerShell):
    winget install FiloSottile.mkcert
    mkcert -install      # crea la autoridad local y la añade al almacén de Windows
Después abre una terminal nueva y repite la orden. Guía completa en
docs/operacion/https-local.md"
}

# Ruta POSIX de la autoridad de mkcert (en Windows, mkcert devuelve C:\...).
mkcert_caroot() {
    caroot=$(mkcert -CAROOT) || kapataz_die "mkcert -CAROOT ha fallado"
    if command -v cygpath >/dev/null 2>&1; then
        caroot=$(cygpath -u "$caroot")
    fi
    printf '%s\n' "$caroot"
}

# Deja en .local-tls/ un certificado de mkcert para $1, localhost y 127.0.0.1.
# Lo regenera si falta, si cambia la IP o si cambia la autoridad de mkcert.
ensure_certificate() {
    ip=$1
    wanted="$ip localhost 127.0.0.1"
    reason=
    if [ ! -s "$tls_dir/cert.pem" ] || [ ! -s "$tls_dir/key.pem" ]; then
        reason="no hay certificado"
    elif [ "$(cat "$tls_dir/hosts" 2>/dev/null || true)" != "$wanted" ]; then
        reason="ha cambiado la IP"
    elif command -v mkcert >/dev/null 2>&1 \
        && ! cmp -s "$(mkcert_caroot)/rootCA.pem" "$tls_dir/rootCA.pem"; then
        reason="ha cambiado la autoridad de mkcert"
    fi
    if [ -z "$reason" ]; then
        kapataz_log "certificado vigente en .local-tls/ para $wanted"
        return 0
    fi

    command -v mkcert >/dev/null 2>&1 || mkcert_missing
    caroot=$(mkcert_caroot)
    # Sin autoridad instalada, mkcert crearía una nueva que ningún navegador
    # reconoce. Instalarla toca el almacén de confianza: lo hace la persona.
    [ -s "$caroot/rootCA.pem" ] \
        || kapataz_die "mkcert no tiene autoridad local en $caroot. Ejecuta antes, una sola vez: mkcert -install"

    kapataz_log "generando el certificado de $wanted ($reason)"
    mkdir -p "$tls_dir"
    # Rutas relativas: mkcert es un ejecutable de Windows y no entiende /d/...
    # Encadenado con &&: dentro de «( ) ||», set -e no corta el subshell.
    (
        cd "$tls_dir" \
            && rm -f cert.pem.tmp key.pem.tmp \
            && mkcert -cert-file cert.pem.tmp -key-file key.pem.tmp "$ip" localhost 127.0.0.1 \
            && mv cert.pem.tmp cert.pem \
            && mv key.pem.tmp key.pem
    ) || kapataz_die "mkcert no ha podido generar el certificado"
    # Solo el certificado público de la autoridad, para instalarlo en el móvil.
    # rootCA-key.pem no sale nunca de la carpeta de mkcert.
    cp "$caroot/rootCA.pem" "$tls_dir/rootCA.pem"
    cp "$caroot/rootCA.pem" "$tls_dir/rootCA.crt"
    printf '%s\n' "$wanted" >"$tls_dir/hosts"
}

# Subredes IPv4 de kronoqr-app separadas por comas, para FORWARDED_ALLOW_IPS.
kronoqr_app_subnets() {
    subnets=$(docker network inspect kronoqr-app \
        --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}') \
        || kapataz_die "no se puede inspeccionar la red kronoqr-app"
    allow=
    for subnet in $subnets; do
        case $subnet in
            *[!0-9./]*) ;;
            *.*.*.*/*) allow=${allow:+$allow,}$subnet ;;
        esac
    done
    [ -n "$allow" ] || kapataz_die "kronoqr-app no tiene subred IPv4 en su IPAM"
    printf '%s\n' "$allow"
}

main() {
    https_ip=
    while [ "$#" -gt 0 ]; do
        case $1 in
            --https)
                [ "$#" -ge 2 ] || kapataz_die "--https necesita la IP del portátil en la red local"
                https_ip=$2
                shift 2
                ;;
            --https=*)
                https_ip=${1#--https=}
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            *)
                usage >&2
                kapataz_die "argumento desconocido: $1"
                ;;
        esac
    done

    kapataz_require docker git
    [ -r "$local_env_file" ] \
        || kapataz_die "falta $local_env_file: cp .env.local.example .env.local"

    if [ -n "$https_ip" ]; then
        is_private_ipv4 "$https_ip" \
            || kapataz_die "«$https_ip» no es una IPv4 privada (10.x, 172.16-31.x o 192.168.x). Usa la IP del portátil en la red local (ipconfig)"
        ensure_certificate "$https_ip"
    fi

    if ! docker network inspect kronoqr-app >/dev/null 2>&1; then
        kapataz_log "creando la red local kronoqr-app"
        docker network create kronoqr-app >/dev/null
    fi

    # Variables de docker-compose.local.yml. Se fijan siempre, en los dos
    # modos, para que ningún valor suelto del entorno cambie el modo.
    if [ -n "$https_ip" ]; then
        KAPATAZ_LOCAL_COOKIE_SECURE=true
        KAPATAZ_LOCAL_PUBLIC_BASE_URL=https://$https_ip:$tls_port
        KAPATAZ_LOCAL_FORWARDED_ALLOW_IPS=$(kronoqr_app_subnets)
        KAPATAZ_LOCAL_LAN_IP=$https_ip
    else
        KAPATAZ_LOCAL_COOKIE_SECURE=false
        KAPATAZ_LOCAL_PUBLIC_BASE_URL=http://localhost:8000
        KAPATAZ_LOCAL_FORWARDED_ALLOW_IPS=127.0.0.1
        KAPATAZ_LOCAL_LAN_IP=127.0.0.1
    fi
    export KAPATAZ_LOCAL_COOKIE_SECURE KAPATAZ_LOCAL_PUBLIC_BASE_URL \
        KAPATAZ_LOCAL_FORWARDED_ALLOW_IPS KAPATAZ_LOCAL_LAN_IP

    GIT_COMMIT=$(git -C "$KAPATAZ_ROOT" rev-parse HEAD 2>/dev/null || printf 'local')
    if ! git -C "$KAPATAZ_ROOT" diff --quiet HEAD -- 2>/dev/null; then
        GIT_COMMIT="$GIT_COMMIT-dirty"
    fi
    export GIT_COMMIT

    if [ "${KAPATAZ_SKIP_BUILD:-0}" != 1 ]; then
        kapataz_log "construyendo la imagen ($GIT_COMMIT)"
        local_compose build kapataz
    fi

    if [ -z "$https_ip" ] && docker container inspect "$tls_container" >/dev/null 2>&1; then
        kapataz_log "parando $tls_container: modo HTTP"
        local_compose --profile https rm --stop --force "$tls_container"
    fi

    kapataz_log "arrancando kapataz-db"
    local_compose up --detach --wait --wait-timeout "$KAPATAZ_WAIT_TIMEOUT" kapataz-db
    kapataz_log "aplicando migraciones"
    local_compose run --rm --no-deps kapataz-tools
    kapataz_log "arrancando kapataz y kapataz-worker"
    local_compose up --detach --no-build --wait --wait-timeout "$KAPATAZ_WAIT_TIMEOUT" \
        kapataz kapataz-worker

    if [ -n "$https_ip" ]; then
        kapataz_log "arrancando $tls_container (FORWARDED_ALLOW_IPS=$KAPATAZ_LOCAL_FORWARDED_ALLOW_IPS)"
        # --force-recreate: nginx lee el certificado al arrancar.
        local_compose --profile https up --detach --no-build --force-recreate \
            --wait --wait-timeout "$KAPATAZ_WAIT_TIMEOUT" "$tls_container"
        kapataz_log "listo: $KAPATAZ_LOCAL_PUBLIC_BASE_URL (en este portátil, también https://127.0.0.1:$tls_port)"
    else
        kapataz_log "listo: http://localhost:8000"
    fi
}

main "$@"
