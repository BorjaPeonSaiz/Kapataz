#!/bin/sh
# Comprueba, sobre el modelo resuelto de Compose (docker compose config), que
# las credenciales del rol propietario de PostgreSQL (kapataz_owner, no sujeto
# a RLS; ADR-024) y las del superusuario solo llegan a kapataz-db y, la del
# propietario, a kapataz-tools para las migraciones. kapataz, kapataz-worker y
# cualquier otro servicio no deben recibirlas, ni en producción ni en local.
#
#   sh deploy/check-compose-env.sh                        # plantillas, los dos modos (CI)
#   sh deploy/check-compose-env.sh local .env.local       # un fichero real, modo local
#   sh deploy/check-compose-env.sh production .env        # un fichero real, modo producción
#
# Sin argumentos usa .env.local.example y .env.production.example, con
# contraseñas de prueba en una copia temporal que se borra al salir.
# Nunca imprime valores: solo el servicio y el nombre de la variable.
#
# Necesita docker compose y jq.

set -eu

KAPATAZ_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
# shellcheck source=deploy/lib.sh
. "$KAPATAZ_ROOT/deploy/lib.sh"

check_tmp_files=
cleanup() {
    for check_tmp in $check_tmp_files; do
        rm -f "$check_tmp"
    done
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

# Una línea por cada infracción; nada si todo está bien.
# shellcheck disable=SC2016 # $variables de jq, no del shell
jq_program='
  (.services["kapataz-db"].environment // {}) as $db
  | ($db.KAPATAZ_OWNER_DB_PASSWORD // "") as $owner
  | ($db.POSTGRES_PASSWORD // "") as $super
  | def leaks($v):
      ($v | ascii_downcase | contains("kapataz_owner"))
      or ($owner != "" and ($v | contains($owner)))
      or ($super != "" and ($v | contains($super)));
    (if $owner == "" then "kapataz-db: KAPATAZ_OWNER_DB_PASSWORD vacía o ausente" else empty end),
    (.services
      | to_entries[]
      | select(.key != "kapataz-db" and .key != "kapataz-tools")
      | .key as $svc
      | (.value.environment // {})
      | to_entries[]
      | (.value // "" | tostring) as $v
      | select(
          leaks($v)
          or (.key == "DATABASE_MIGRATION_URL" and $v != "")
          or (.key == "KAPATAZ_OWNER_DB_PASSWORD" and $v != "")
          or (.key == "POSTGRES_PASSWORD" and $v != ""))
      | "\($svc): \(.key) lleva credenciales del propietario o del superusuario"),
    (.services["kapataz-tools"] as $tools
      | if $tools == null then "falta el servicio kapataz-tools"
        else
          ($tools.environment // {}) as $env
          | (if (($env.DATABASE_MIGRATION_URL // "")
                  | startswith("postgresql+asyncpg://kapataz_owner:" + $owner + "@kapataz-db:"))
             then empty
             else "kapataz-tools: DATABASE_MIGRATION_URL no es la URL del propietario" end),
            ($env | to_entries[]
              | (.value // "" | tostring) as $v
              | select(($super != "" and ($v | contains($super)))
                  or (.key == "POSTGRES_PASSWORD" and $v != ""))
              | "kapataz-tools: \(.key) lleva credenciales del superusuario")
        end)
'

# check_mode <local|production> <fichero .env, relativo a la raíz del repositorio>
# Relativo porque env_file se resuelve desde el directorio del proyecto y
# Compose en Windows no entiende rutas /d/... en KAPATAZ_ENV_FILE.
check_mode() {
    check_mode_name=$1
    check_env_file=$2
    [ -r "$KAPATAZ_ROOT/$check_env_file" ] || kapataz_die "no se puede leer $check_env_file"

    set -- --project-directory "$KAPATAZ_ROOT" --env-file "$KAPATAZ_ROOT/$check_env_file" \
        --file "$KAPATAZ_ROOT/docker-compose.yml"
    case $check_mode_name in
        local) set -- "$@" --file "$KAPATAZ_ROOT/docker-compose.local.yml" --profile https ;;
        production) ;;
        *) kapataz_die "modo desconocido: $check_mode_name (local o production)" ;;
    esac
    set -- "$@" --profile tools

    # Las variables del entorno mandan sobre --env-file: así env_file apunta
    # al mismo fichero que se comprueba, como en el servidor y en local.
    check_config=$(KAPATAZ_ENV_FILE=$check_env_file \
        KAPATAZ_IMAGE_TAG=${KAPATAZ_IMAGE_TAG:-check} \
        docker compose "$@" config --format json) \
        || kapataz_die "$check_mode_name: docker compose config ha fallado"

    check_errors=$(printf '%s\n' "$check_config" | jq -r "$jq_program") \
        || kapataz_die "$check_mode_name: jq ha fallado"
    if [ -n "$check_errors" ]; then
        printf '%s\n' "$check_errors" | while IFS= read -r check_line; do
            kapataz_log "ERROR: $check_mode_name: $check_line"
        done
        return 1
    fi
    kapataz_log "$check_mode_name: kapataz_owner solo llega a kapataz-db y kapataz-tools ($check_env_file)"
}

# Copia temporal de una plantilla, dentro del repositorio (ignorada por git y
# por .dockerignore como .env.*), con contraseñas de prueba. Deja en
# template_copy_file su ruta relativa a la raíz.
template_copy() {
    check_tmp=$(mktemp "$KAPATAZ_ROOT/.env.check.XXXXXX")
    check_tmp_files="$check_tmp_files $check_tmp"
    sed \
        -e 's/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=checksuperuser0000000000000000000/' \
        -e 's/^KAPATAZ_OWNER_DB_PASSWORD=.*/KAPATAZ_OWNER_DB_PASSWORD=checkowner00000000000000000000000/' \
        -e 's/^KAPATAZ_APP_DB_PASSWORD=.*/KAPATAZ_APP_DB_PASSWORD=checkapp0000000000000000000000000/' \
        -e 's/^SECRET_KEY=$/SECRET_KEY=checksecret000000000000000000000000/' \
        "$KAPATAZ_ROOT/$1" >"$check_tmp"
    template_copy_file=${check_tmp#"$KAPATAZ_ROOT"/}
}

# Ruta de $1 relativa a la raíz del repositorio; debe estar dentro de ella.
root_relative() {
    rel_dir=$(CDPATH='' cd -- "$(dirname -- "$1")" && pwd -P) \
        || kapataz_die "no existe el directorio de $1"
    case $rel_dir/ in
        "$KAPATAZ_ROOT"/*) ;;
        *) kapataz_die "$1 debe estar dentro de $KAPATAZ_ROOT" ;;
    esac
    rel_dir=${rel_dir#"$KAPATAZ_ROOT"}
    rel_dir=${rel_dir#/}
    printf '%s\n' "${rel_dir:+$rel_dir/}$(basename -- "$1")"
}

main() {
    kapataz_require docker jq
    case $# in
        0)
            status=0
            template_copy .env.local.example
            check_mode local "$template_copy_file" || status=1
            template_copy .env.production.example
            check_mode production "$template_copy_file" || status=1
            exit "$status"
            ;;
        2)
            check_mode "$1" "$(root_relative "$2")"
            ;;
        *)
            kapataz_die "uso: sh deploy/check-compose-env.sh [local|production <fichero .env>]"
            ;;
    esac
}

main "$@"
