# Despliegue de Kapataz

Procedimiento de despliegue en producción (`https://kapataz.kodigolab.es`) y en local, según ADR-014. Hasta cerrar el Bloque 12 solo se usa en local: el primer despliegue en el servidor se hace en ese bloque (plan maestro, §1.5). Este documento es la única guía para desplegar: la Fase 0 del plan de verificación exige poder montar un servidor vacío siguiendo solo `docs/operacion/`.

## 1. Qué se despliega

| Pieza | Qué es | Redes | Puertos publicados |
|---|---|---|---|
| `kapataz` | api (FastAPI + build de Vue), `uvicorn` en `0.0.0.0:8000` | `kapataz-internal`, `kapataz-egress`, `kronoqr-app` | ninguno |
| `kapataz-worker` | `python -m kapataz.worker` | `kapataz-internal`, `kapataz-egress` | ninguno |
| `kapataz-db` | `pgvector/pgvector:pg16`, fijada por digest | `kapataz-internal` | ninguno |
| `kapataz-tools` | misma imagen; solo con `run --rm`: migraciones y `kapataz-admin` | `kapataz-internal` | ninguno |

- **Redes:**
  - `kapataz-internal` es `internal: true`: no tiene salida a internet y solo la ven nuestros servicios.
  - `kapataz-egress` da salida a internet a la api y al worker (API de Claude, SMTP).
  - `kronoqr-app` es la red del nginx de KronoQR. Es externa: la crea KronoQR, y solo se une `kapataz`.
- **Volúmenes:** `kapataz-db-data` (PostgreSQL) y `kapataz-uploads` (ficheros, en `/data/uploads`). Tienen nombre fijo y no dependen del nombre del proyecto.
- **Imagen:** `kapataz:<commit>` hasta la 1.0.0 y `kapataz:<versión>` después (ADR-032). Se construye en el propio servidor y nunca se descarga de un registro (`pull_policy: never`). Nunca se usa `latest`.
- **Roles de PostgreSQL** (`deploy/postgres-init/10-roles.sh`, se ejecuta al crear el volumen):
  - `kapataz_owner` es propietario de la base de datos y del esquema; ejecuta las migraciones.
  - `kapataz_app` es el rol de la aplicación, sin `BYPASSRLS`, sin propiedad de tablas y sin permiso para crear objetos.
- **Secretos:** solo en `/opt/kapataz/.env`, con permisos 600. Compose lo usa para interpolar `docker-compose.yml` y lo pasa a los contenedores de la app, con estas diferencias:
  - `kapataz` y `kapataz-worker` reciben `DATABASE_URL` (rol `kapataz_app`) y el resto de la configuración de la app. Las tres contraseñas de PostgreSQL y `DATABASE_MIGRATION_URL` les llegan vacías: nunca tienen credenciales de `kapataz_owner`, que no está sujeto a RLS (ADR-024).
  - `kapataz-tools` recibe lo mismo más `DATABASE_MIGRATION_URL`, la URL de `kapataz_owner`, que `docker-compose.yml` compone con `KAPATAZ_OWNER_DB_PASSWORD` y que Alembic lee del entorno. Esa URL no va en `.env`.
  - `kapataz-db` no recibe `.env`: solo sus tres contraseñas.
  - Lo comprueba `sh deploy/check-compose-env.sh` en el CI, en modo local y en modo producción. En el servidor, `sh deploy/check-compose-env.sh production .env` comprueba el `.env` real sin imprimir ningún valor.

## 2. Entorno local

Requisitos: Docker Desktop (o Docker Engine con Compose v2) y Git Bash en Windows.

```sh
cp .env.local.example .env.local   # la primera vez; solo datos sintéticos
sh deploy/local-up.sh              # construye, migra y arranca; espera a los health checks
```

La app queda en `http://localhost:8000`. `deploy/local-up.sh` crea la red `kronoqr-app` vacía si no existe, para que el Compose sea el mismo que en el servidor.

`docker-compose.local.yml` se usa siempre de forma explícita, nunca con el nombre de override automático de Compose:

```sh
docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml ps
docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml logs -f kapataz
docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml down      # -v borra los datos
```

En local, la api publica `127.0.0.1:8000` y usa `APP_ENV=local`, `COOKIE_SECURE=false` y `EMAIL_BACKEND=fake`. Los contenedores reciben lo mismo que en producción (sección 1): solo `kapataz-tools` tiene la URL de `kapataz_owner`. Un `.env.local` copiado de una plantilla anterior aún lleva la línea `DATABASE_MIGRATION_URL`; se puede borrar, y mientras tanto `kapataz` y `kapataz-worker` la reciben vacía.

### 2.1 HTTPS en la red local

Para entrar desde un móvil real por HTTPS (criterio de terminado del Bloque 1), usa `sh deploy/local-up.sh --https <IP del portátil>`. Añade el proxy `kapataz-local-tls`, un nginx sin root con la configuración de la sección 10 y un certificado de mkcert, en `https://<IP>:8443`. La guía completa, con la instalación de mkcert, el certificado en Android y en iPhone y el cortafuegos de Windows, está en [https-local.md](https-local.md).

Ese modo usa el perfil `https` de Compose: para pararlo todo, añade `--profile https` a `down`.

> En Windows, los `.sh` deben tener finales de línea LF. Con `core.autocrlf=true`, Git los convierte a CRLF al hacer checkout y PostgreSQL no puede ejecutar el script de inicio. Lo evita un `.gitattributes` con `*.sh text eol=lf`.

## 3. Requisitos del servidor

- VPS de la UE con KronoQR. Su nginx (`kronoqr-nginx-1`) ocupa los puertos 80 y 443 y está en la red `kronoqr-app`.
- Docker Engine con el plugin Compose v2 (2.24 o posterior), `git` y `age` (`apt install age`), para las copias cifradas.
- Un usuario de despliegue con acceso por clave SSH y en el grupo `docker`. No se despliega como root.
- Cortafuegos con solo 22, 80 y 443 abiertos. Kapataz no publica ningún puerto.

## 4. Primer despliegue

### 4.1 Preparar `/opt/kapataz`

```sh
sudo mkdir -p /opt/kapataz && sudo chown "$USER": /opt/kapataz
git clone https://github.com/BorjaPeonSaiz/Kapataz.git /opt/kapataz
cd /opt/kapataz
cp .env.production.example .env
chmod 600 .env
```

Rellena `.env`:

- Cada contraseña y la `SECRET_KEY` con `openssl rand -hex 32`. Solo letras y números: van dentro de URL, y Compose interpreta el carácter `$`.
- `FORWARDED_ALLOW_IPS` con la subred real de `kronoqr-app` (se espera `172.18.0.0/16`). Se comprueba con:

  ```sh
  docker network inspect kronoqr-app --format '{{(index .IPAM.Config 0).Subnet}}'
  ```

- `SMTP_*` con el proveedor de la UE. `LLM_BACKEND=fake` en el Bloque 1.

Las contraseñas de PostgreSQL solo se aplican al crear el volumen `kapataz-db-data`. Cambiarlas después en `.env` no cambia las de la base de datos: se cambian con `ALTER ROLE` y luego en `.env`.

### 4.2 Clave de las copias

La clave privada de `age` se genera y se guarda **fuera del servidor**, por ejemplo en el gestor de contraseñas. En el servidor solo queda la clave pública:

```sh
# En el portátil:
age-keygen -o kapataz-backup.key        # guárdala fuera del servidor y del repositorio
age-keygen -y kapataz-backup.key        # imprime la clave pública (age1...)

# En el servidor:
mkdir -p /opt/kapataz/.deploy
echo 'age1...' > /opt/kapataz/.deploy/backup-recipients.txt
sudo mkdir -p /var/backups/kapataz && sudo chown "$USER": /var/backups/kapataz
```

### 4.3 Desplegar

```sh
cd /opt/kapataz
sh deploy/deploy.sh <commit de main>
```

En el primer despliegue no hay copia, porque la base de datos aún no existe. `kapataz-db` se crea, `10-roles.sh` crea los roles y después se aplican las migraciones.

### 4.4 nginx

El administrador añade el bloque de la sección 10. Hasta entonces, el health check de `deploy.sh` ya comprueba la app desde `kronoqr-app`, pero no por HTTPS.

### 4.5 Cuenta de cortesía

Mientras queden pendientes legales, el registro está cerrado (RN-13). Las cuentas de demostración se crean con `kapataz-admin`:

```sh
cd /opt/kapataz
sh deploy/compose.sh run --rm kapataz-tools kapataz-admin create-user --email persona@example.com
```

`kapataz-tools` solo está en `kapataz-internal`: llega a la base de datos, pero no a internet ni a `kronoqr-app`.

## 5. Despliegue normal

Antes de desplegar, en local:

1. El PR está integrado en `main` con el CI en verde.
2. Ese mismo commit se ha probado con `sh deploy/local-up.sh`.
3. Desde la 1.0.0, además, la migración se ha probado sobre una copia de producción restaurada en local (sección 7.3).

En el servidor:

```sh
cd /opt/kapataz
sh deploy/deploy.sh <commit>
```

`deploy.sh` hace, por orden:

1. `git fetch` y comprueba que el commit está en `origin/main` y que el árbol de trabajo no tiene cambios.
2. Construye `kapataz:<commit>` desde `git archive`, así que solo entra lo versionado. La versión en marcha sigue funcionando mientras tanto.
3. Deja `/opt/kapataz` en ese commit, para que `docker-compose.yml` coincida con la imagen.
4. Hace una copia cifrada de la base de datos (`deploy/backup-db.sh pre-deploy-<commit>`). Si falla, no despliega.
5. Ejecuta `alembic upgrade head` con `kapataz-tools`. Si falla, no despliega y la versión anterior sigue en marcha.
6. `up -d` de `kapataz` y `kapataz-worker` con la nueva etiqueta, y espera a sus health checks.
7. Pide `/api/health` desde un contenedor en `kronoqr-app`, por el nombre `kapataz`, como lo haría nginx. Exige que `kapataz` resuelva a un solo contenedor y que la versión que informa sea la desplegada.

Si falla cualquier paso desde el 3, vuelve al commit y a la etiqueta anteriores. El estado queda en `.deploy/current`, `.deploy/previous` y `.deploy/history`.

Las migraciones no se deshacen solas. Toda migración debe ser compatible con la versión anterior, y una irreversible se despliega en dos pasos compatibles. Si una migración rompe datos, se restaura la copia del paso 4 (sección 7.2).

Después, las comprobaciones de la sección 8.

Para operar con la versión en marcha:

```sh
sh deploy/compose.sh ps
sh deploy/compose.sh logs --tail=200 kapataz
```

Las imágenes antiguas no se borran solas. Conserva al menos las dos últimas, para poder volver atrás:

```sh
docker image ls kapataz
docker image rm kapataz:<etiqueta antigua>
```

## 6. Vuelta atrás

```sh
cd /opt/kapataz
sh deploy/rollback.sh              # a la etiqueta de .deploy/previous
sh deploy/rollback.sh <etiqueta>   # a una etiqueta concreta (su imagen debe existir)
```

`rollback.sh` deja el árbol en el commit de esa etiqueta y recrea solo `kapataz` y `kapataz-worker`, con la misma espera de health checks y la comprobación desde `kronoqr-app`. La base de datos no se toca. Si la etiqueta destino no queda sana, vuelve a la que estaba.

Probado en local el 12/11/2026 con tres commits: despliegue inicial, despliegue con copia, despliegue roto que vuelve solo al anterior, y `rollback.sh`.

## 7. Copias de seguridad

### 7.1 Hacer una copia

```sh
sh deploy/backup-db.sh [etiqueta]
```

Hace `pg_dump` en formato custom dentro de `kapataz-db`, lo cifra con `age` hacia la clave pública y lo deja en `/var/backups/kapataz/kapataz-<fecha UTC>-<etiqueta>.dump.age`, con permisos 600. Borra las copias locales de más de 14 días (`BACKUP_RETENTION_DAYS`).

> **Pendiente del Bloque 10 (RNF-15):** envío de cada copia fuera del servidor, a un almacenamiento en la UE, archivado continuo de WAL (RPO ≤ 15 min), copia de `kapataz-uploads` y tarea programada. Hasta entonces, las copias se quedan en el propio VPS y no protegen de su pérdida.

### 7.2 Restaurar una copia en producción

Solo con la app parada y tras decidirlo de forma explícita: se pierde todo lo escrito después de la copia.

```sh
cd /opt/kapataz
sh deploy/compose.sh stop kapataz kapataz-worker
# Copia el .dump.age al portátil, descífralo allí y súbelo por un canal seguro;
# la clave privada nunca va al servidor.
sh deploy/compose.sh exec -T kapataz-db \
  pg_restore --username=postgres --dbname=kapataz --clean --if-exists --exit-on-error < kapataz.dump
sh deploy/compose.sh up -d --wait kapataz kapataz-worker
shred -u kapataz.dump
```

### 7.3 Simulacro de restauración en local

Una copia que no se ha restaurado no cuenta como copia. En el portátil, con un volumen local limpio:

```sh
age --decrypt --identity kapataz-backup.key kapataz-<fecha>.dump.age > /tmp/kapataz.dump
C="docker compose --env-file .env.local -f docker-compose.yml -f docker-compose.local.yml"
$C down -v && $C up -d --wait kapataz-db
$C exec -T kapataz-db pg_restore --username=postgres --dbname=kapataz --clean --if-exists --exit-on-error < /tmp/kapataz.dump
$C run --rm --no-deps kapataz-tools          # alembic upgrade head de la versión nueva
rm /tmp/kapataz.dump
```

Anota la fecha, el tamaño y el tiempo que tarda (RTO). El cifrado, la restauración en una base de datos nueva, la propiedad de las tablas y RLS se probaron el 12/11/2026.

## 8. Comprobaciones tras desplegar

Desde el portátil, salvo que se indique otra cosa.

| Qué | Cómo | Esperado |
|---|---|---|
| HTTP redirige a HTTPS | `curl -sI http://kapataz.kodigolab.es/` | `301` a `https://kapataz.kodigolab.es/` |
| HTTPS y health | `curl -s https://kapataz.kodigolab.es/api/health` | `200`, `"status":"ok"` y `version` igual al commit desplegado |
| HSTS y cabeceras | `curl -sI https://kapataz.kodigolab.es/` | `strict-transport-security: max-age=31536000; includeSubDomains` una sola vez, más CSP, `x-content-type-options` y `x-frame-options` |
| SSE sin búfer | Con sesión iniciada (cookies y `X-CSRF-Token`): `curl -sN -o /dev/null -w '%{time_starttransfer} %{time_total}\n' -d '{"message":"hola"}' -H 'Content-Type: application/json' ... https://kapataz.kodigolab.es/api/chat` | El primer byte llega en centésimas y el total tarda lo que tarda el `FakeLlm`. Si los dos tiempos son casi iguales, hay búfer. nginx consume `X-Accel-Buffering` y no la reenvía al cliente |
| IP real del cliente | `tests/e2e_api/test_transporte.py` contra producción (ADR-014, `qa-testing`) | La api ve la IP pública del portátil, no `172.18.x.x`. Los logs no registran la IP, porque es un dato personal |
| Tamaño de subida | Petición de 20 MB a un endpoint de subida (desde el Bloque 4) | La rechaza o la acepta la app, no nginx con `413` |
| `kapataz-db` no es accesible desde `kronoqr-app` | En el servidor: comandos de abajo | No resuelve el nombre y no conecta por IP |
| `kapataz` resuelve a un solo contenedor | Lo comprueba `deploy.sh` en cada despliegue | Una sola dirección |
| Puertos 8000 y 5432 cerrados desde fuera | `nc -vz -w 5 <IP pública> 8000` y `nc -vz -w 5 <IP pública> 5432` (o `nmap -Pn -p 22,80,443,5432,8000 <IP pública>`) | Solo responden 22, 80 y 443 |

Prueba de red en el servidor:

```sh
# Por nombre: no debe resolver.
docker run --rm --network kronoqr-app --entrypoint python kapataz:"$(cat .deploy/current)" \
  -c "import socket; socket.getaddrinfo('kapataz-db', 5432)"
# -> socket.gaierror: Name or service not known

# Por IP: no debe conectar.
DB_IP=$(docker inspect -f '{{(index .NetworkSettings.Networks "kapataz-internal").IPAddress}}' kapataz-kapataz-db-1)
docker run --rm --network kronoqr-app --entrypoint python kapataz:"$(cat .deploy/current)" \
  -c "import socket; socket.create_connection(('$DB_IP', 5432), timeout=3)"
# -> TimeoutError u OSError
```

El resultado de estas comprobaciones se anota en el PR del bloque.

## 9. Problemas frecuentes

- **`Falta KAPATAZ_IMAGE_TAG`:** se ha llamado a `docker compose` directamente. En el servidor se usa `sh deploy/compose.sh`, y en local, `sh deploy/local-up.sh` o `--env-file .env.local`.
- **`network kronoqr-app declared as external, but could not be found`:** en local, ejecuta `sh deploy/local-up.sh`, que la crea. En el servidor, KronoQR no está en marcha.
- **`502` en nginx:** `kapataz` no está sano o no está en `kronoqr-app`. Revisa `sh deploy/compose.sh ps` y `docker network inspect kronoqr-app`.
- **La IP de todos los clientes es `172.18.x.x`:** `FORWARDED_ALLOW_IPS` no coincide con la subred de `kronoqr-app`, o nginx no envía `X-Forwarded-For`. uvicorn 0.54.0, fijado en `backend/pyproject.toml`, admite rangos CIDR en esa opción.

## 11. Prueba del bloque de nginx en local

El bloque de la sección 10 se probó el 12/11/2026 con `nginx:1.29` en la red `kronoqr-app` local y un certificado autofirmado:

- `nginx -t` es correcto.
- nginx arranca sin que exista `kapataz` (responde `502`) y empieza a enrutar cuando aparece, sin recargarlo.
- HTTP redirige con `301` a HTTPS.
- `/api/health` responde `200` con HSTS una sola vez.
- El chat por SSE da el primer byte a los 0,02 s, con un total de 0,83 s, así que no hay búfer.

## 10. Para el administrador del VPS

Kapataz se despliega en `/opt/kapataz` con el proyecto de Compose `kapataz`. Solo el contenedor `kapataz` se une a la red `kronoqr-app`, y escucha en el puerto 8000 sin TLS. No publica ningún puerto en el host. HSTS y las cabeceras de seguridad las pone la app.

Bloque para la configuración del nginx de KronoQR (`kronoqr-nginx-1`):

```nginx
# Kapataz — https://kapataz.kodigolab.es (ADR-014)

server {
    listen 80;
    listen [::]:80;
    server_name kapataz.kodigolab.es;

    # Si este nginx atiende el reto ACME por HTTP para emitir o renovar
    # certificados, copia aquí la misma location que usan los demás dominios
    # (normalmente /.well-known/acme-challenge/) antes de la redirección.

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    # Con nginx 1.25.1 o posterior; en versiones anteriores, usa
    # «listen 443 ssl http2;» y quita esta línea.
    http2 on;
    server_name kapataz.kodigolab.es;

    # Certificado de kapataz.kodigolab.es: el mismo mecanismo y la misma
    # ubicación que ya usan los demás dominios de este nginx.
    # ssl_certificate     <fullchain de kapataz.kodigolab.es>;
    # ssl_certificate_key <clave privada de kapataz.kodigolab.es>;
    # Si hay un include común de parámetros TLS, inclúyelo aquí también.

    # Sin log de acceso: registraría la IP del cliente y la query, que lleva el
    # token de /verificar-email (ADR-015; la app tampoco registra la query).
    # Si el administrador necesita uno, que use $uri en vez de $request.
    access_log off;

    # No añadas Strict-Transport-Security aquí: la pone la app. Si un include
    # común ya la añade, comprueba que no sale duplicada.

    # Subidas de PDF (Bloque 4) y audio (Bloque 9); la app aplica límites
    # menores por endpoint.
    client_max_body_size 50m;

    # Resolver interno de Docker. Con la dirección en una variable, nginx
    # resuelve «kapataz» al atender cada petición y no al arrancar: así
    # nginx arranca aunque Kapataz no exista todavía, y sigue la IP nueva
    # cuando Docker recrea el contenedor en cada despliegue.
    resolver 127.0.0.11 valid=10s ipv6=off;
    resolver_timeout 5s;
    set $kapataz_upstream http://kapataz:8000;

    location / {
        proxy_pass $kapataz_upstream;

        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE del chat: sin búfer ni caché, y conexiones largas.
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

Notas:

- **Variable en `proxy_pass`:** sin parte de URI, nginx pasa la petición original sin cambios, que es lo que necesita la app.
- **Compresión:** no incluyas `text/event-stream` en `gzip_types`, porque el SSE se quedaría en búfer.
- **IP real del cliente:** uvicorn solo acepta `X-Forwarded-*` de la subred de `kronoqr-app` (`172.18.0.0/16`) y toma la IP más a la derecha que no sea de esa subred. Si delante de este nginx hubiera otro proxy o CDN, avísanos.
- **Cuándo recargar:** tras añadir el bloque, ejecuta `docker exec kronoqr-nginx-1 nginx -t` y después `docker exec kronoqr-nginx-1 nginx -s reload`.
- **Comprobación:** `curl -sI https://kapataz.kodigolab.es/api/health` debe devolver `200` con `strict-transport-security`.
- **Copia local (para el equipo de Kapataz):** `deploy/local-tls/kapataz.conf` reproduce este bloque para el HTTPS local ([https-local.md](https-local.md)). Los dos se cambian a la vez.
