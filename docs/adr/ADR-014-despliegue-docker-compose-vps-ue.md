# ADR-014 — Despliegue con Docker Compose en un VPS de la UE

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Modificado:** 2026-11-17. Borja decide que todo se hace en local y que el primer despliegue llega al cerrar el Bloque 12 (plan maestro, §1.5).
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RNF-01, RNF-03, RNF-12, RNF-14, RNF-15, RNF-16, RN-13
- **Se cierra en:** Bloque 12

## Contexto

Kapataz necesita en producción varios procesos permanentes:

- **api:** FastAPI, que también sirve el frontend (ADR-013).
- **worker:** cola de tareas para ingesta, embeddings y transcripción (ADR-026).
- **PostgreSQL** con pgvector (ADR-004).

Delante hace falta un proxy que termine TLS. El VPS ya tiene uno: el contenedor nginx de KronoQR (`kronoqr-nginx-1`), que ocupa los puertos 80 y 443 y gestiona HTTPS. Quien administra el VPS lo confirmó el 12/11/2026 tras revisar la configuración real, y no se puede levantar otro proxy porque esos puertos ya están ocupados.

Requisitos:

- Datos en servidores de la UE (RNF-01).
- Disponibilidad del 99,5 % mensual (RNF-03).
- Solo HTTPS con HSTS; base de datos y servicios internos sin exponer (RNF-12).
- Copias cifradas fuera del servidor, en la UE, con RPO ≤ 15 min y RTO ≤ 4 h (RNF-15).
- 100 cuentas activas a la vez sin incumplir RNF-04 (RNF-16).

Lo opera una sola persona. Hay dos entornos: local y producción, sin staging (Borja, 12/11/2026). Por ahora Kapataz es una demo de portafolio, y Borja quiere tenerla lo más acabada posible en local antes de subirla (17/11/2026).

## Opciones consideradas

1. **Docker Compose en un VPS de la UE, con Caddy propio**
   - Ventajas: sencillo de operar y de reproducir en local; controlamos TLS, HSTS y cabeceras.
   - Inconvenientes: un solo servidor es un punto único de fallo; en el VPS actual no es posible, porque los puertos 80 y 443 ya los ocupa el nginx de KronoQR.
2. **Docker Compose en el VPS de la UE que ya aloja KronoQR, detrás de su proxy nginx**
   - Ventajas: lo mismo que la opción 1, sin un proxy propio que mantener; los certificados ya se gestionan ahí.
   - Inconvenientes: un solo servidor compartido con otro proyecto; HSTS, límites de tamaño y tiempos de espera dependen de la configuración de ese proxy, así que la app no puede dar por hecho nada de eso.
3. **Hosting compartido de webs y WordPress**
   - Ventajas: barato.
   - Inconvenientes: no ejecuta procesos Python permanentes, PostgreSQL ni Whisper. Descartado.
4. **Kubernetes, gestionado o propio**
   - Ventajas: escalado y despliegues graduales.
   - Inconvenientes: complejidad de operación desproporcionada para una persona y para la carga de RNF-16.
5. **Plataforma gestionada de contenedores con base de datos gestionada**
   - Ventajas: menos operación propia.
   - Inconvenientes: hay que encontrar región en la UE, soporte de pgvector y un worker con CPU suficiente para Whisper; menos control sobre copias y red.

## Decisión

Opción 2, aprobada por Borja el 12/11/2026. Sustituye a la opción 1, que era la del plan original.

- **Compose** con `kapataz` (la api), `kapataz-worker` y `kapataz-db` (PostgreSQL). `Dockerfile` y `docker-compose.yml` van en la raíz del repositorio. La api escucha en `0.0.0.0:8000` (`uvicorn kapataz.main:app --host 0.0.0.0 --port 8000`). El proxy es la única entrada desde internet y termina TLS.
- **Dos entornos, sin staging** (Borja, 12/11/2026):
  - **Local:** el mismo `docker-compose.yml` en el portátil, con datos sintéticos. Hasta cerrar el Bloque 12 es el único entorno: ahí se construye y se prueba todo, también desde un móvil real con HTTPS local (mkcert), el modo de pruebas de Stripe y la prueba de carga.
  - **Producción:** `https://kapataz.kodigolab.es`, en el VPS, con el proyecto de Compose `kapataz` y los secretos en `/opt/kapataz/.env`. nginx enruta a `kapataz:8000`. El primer despliegue se hace al cerrar el Bloque 12.
  - **Hasta cerrar los pendientes legales, producción solo tiene datos de demostración.** El registro está cerrado y solo hay cuentas de cortesía en el espacio de demostración, con datos sintéticos (RN-13). Por eso ahí se ejecuta la Parte II: la prueba de carga, el escaneo ZAP y las pruebas de pago y de envío con las claves de pruebas de Stripe y del proveedor de Verifactu. Las claves reales solo entran al cerrar su pendiente legal y nunca conviven con las de pruebas en el mismo `.env`.
  - **Cuando se abra el registro, cada despliegue tocará datos reales.** Antes de cada despliegue se hace una copia de la base de datos y se comprueba que la migración se aplica sobre una copia restaurada en local. Si algo falla, se vuelve a la etiqueta anterior.
  - Si algún día hay un segundo entorno en el VPS, cada uno necesita un alias propio en `kronoqr-app`. Con el mismo `docker-compose.yml`, Docker registraría el nombre `kapataz` para los dos y nginx repartiría el tráfico entre ellos.
- **Lo que la app no delega en el proxy:** las cabeceras de seguridad, incluida HSTS (RNF-12), las pone un middleware de FastAPI en cada respuesta. Así no dependen de la configuración del panel.
- **Redes** (configuración real del VPS, revisada por el proveedor el 12/11/2026). El VPS es el mismo que aloja KronoQR, y su proxy es el contenedor nginx de KronoQR, que ocupa los puertos 80 y 443.
  - Solo el servicio `kapataz` se une a la red Docker externa compartida `kronoqr-app`, por la que el proxy llega a `http://kapataz:8000`.
  - PostgreSQL va solo en una red interna propia (`kapataz-internal`, con `internal: true`, sin salida a internet), a la que también se unen `kapataz` y el worker. Así ningún contenedor de KronoQR llega a nuestra base de datos.
  - `kapataz` y el worker comparten además una red de salida propia (`kapataz-egress`), porque los dos llaman a servicios externos: Claude, y más adelante Stripe, SMTP y el proveedor de Verifactu. El worker no entra en `kronoqr-app`.
  - Los servicios internos llevan nombres únicos (`kapataz-db`, `kapataz-worker`). En la red compartida, un nombre genérico como `db` podría resolverse al contenedor de KronoQR.
  - Ningún servicio publica puertos: ni en la IP pública ni en `127.0.0.1`.
- **Proxies de confianza:** uvicorn arranca con `--proxy-headers` y `--forwarded-allow-ips=172.18.0.0/16`, la subred de `kronoqr-app`. No se fija la IP actual del proxy (172.18.0.7), porque Docker la cambia al recrear el contenedor. Antes de usarlo en el Bloque 1 hay que comprobar en la documentación de uvicorn que admite rangos CIDR en esa opción.
- **Configuración que el administrador añade al proxy para `kapataz.kodigolab.es`** (al desplegar la primera versión, en el Bloque 12):
  - Redirección de `http://` a `https://`.
  - `proxy_set_header` de `Host`, `X-Real-IP`, `X-Forwarded-For` y `X-Forwarded-Proto`.
  - Para el SSE del chat: `proxy_http_version 1.1`, `proxy_buffering off`, `proxy_cache off`, y `proxy_read_timeout` y `proxy_send_timeout` de 300 s. Además, la app envía `X-Accel-Buffering: no` en las respuestas SSE, por si el búfer se reactivara.
  - `client_max_body_size 50m`. El límite general actual del proxy es de 8 MB. La app fija después límites propios por endpoint para PDF (Bloque 4) y audio (Bloque 9), siempre por debajo de 50 MB.
- **Quién ve el tráfico en claro:** el proxy termina TLS en el mismo VPS, bajo la misma administración. No entra ningún tercero nuevo; el proveedor del VPS ya figura como subencargado («el alojamiento») en el contrato de encargo.
- **Imágenes:** Dockerfile multietapa sin root, fijadas por digest (ADR-022). Se identifican por commit hasta la 1.0.0 y por versión desde entonces (ADR-032).
- **Despliegue manual, por imagen identificada.** Nunca se usa `latest` ni se despliega en cada push.
  - Hasta la 1.0.0, la etiqueta es el commit (`kapataz:<sha>`), según ADR-032; desde la 1.0.0, la versión (`kapataz:1.0.0`).
  - Pasos: construir la imagen, ejecutar el Compose con esa etiqueta, comprobar `/api/health`, comprobar HTTPS y SSE.
  - Vuelta atrás: volver a la etiqueta anterior y recrear solo el servicio `kapataz`.
  - Migraciones controladas, y una migración irreversible se despliega en dos pasos compatibles.
  - `/api/health` comprueba la base de datos y la API de Claude por separado.
- **Secretos** en `/opt/kapataz/.env`, en el servidor, fuera del repositorio y de las imágenes; en local, un `.env` que nunca se versiona y nunca lleva claves de producción. Ahí van `DATABASE_URL`, la clave de sesión, `ANTHROPIC_API_KEY` y, más adelante, las de Stripe y del proveedor de Verifactu.
- **Volúmenes persistentes:** `kapataz-db-data` para PostgreSQL y `kapataz-uploads` para los ficheros (`FileStoragePort`). Ningún dato vive solo dentro de un contenedor.
- **Copias** cifradas fuera del servidor, en la UE, con archivado de WAL y simulacros de restauración.
- **Cada cambio se prueba en local** con el mismo Compose antes de desplegarlo; no hay staging.

El Bloque 10 deja preparados en local el despliegue, las copias, la observabilidad y la prueba de carga. El Bloque 12 cierra este ADR con el primer despliegue y las condiciones del proxy comprobadas en producción.

## Consecuencias

- **Positivas**
  - Infraestructura que entiende y opera una persona.
  - El entorno de desarrollo es el mismo Compose.
- **Negativas y mitigación**
  - Punto único de fallo → RNF-03 admite unas 3,6 horas de caída al mes; monitor externo de disponibilidad, alertas con runbook y restauración probada dentro del RTO de 4 h.
  - CPU compartida entre API, OCR, embeddings y Whisper → todo lo pesado va al worker con concurrencia limitada; RNF-14 y RNF-16 medidos.
  - Despliegue fallido → la versión anterior sigue funcionando y la vuelta atrás está probada.
  - TLS y parte del borde quedan en manos del proxy de KronoQR → HSTS y cabeceras en la app; las condiciones del proxy se prueban en producción en el Bloque 12, antes de que haya usuarios reales, y otra vez en la Parte II.
  - Desplegar tan tarde hace que los fallos que solo aparecen en el servidor (proxy, red compartida, TLS) se descubran al final → el Bloque 12 empieza por el despliegue, y la Parte II se hace después en producción, antes de la 1.0.0.
  - Sin staging, un fallo que no aparece en local llega directo a producción → mientras queden pendientes legales no hay datos reales; después, copia antes de cada despliegue, migración probada sobre una copia restaurada en local y vuelta atrás por etiqueta.
  - VPS compartido con KronoQR: CPU, memoria y disco compartidos, y una caída del proxy de KronoQR tumba también Kapataz → concurrencia limitada en el worker, RNF-14 y RNF-16 medidos en este VPS, y monitor externo de disponibilidad para Kapataz.
  - Cualquier contenedor de `kronoqr-app` puede enviar `X-Forwarded-For` y ser aceptado como proxy → solo se une a esa red el servicio `kapataz`, y el riesgo se acepta porque los dos proyectos los opera la misma persona (T-69).
- **Qué haría reconsiderarla**
  - Que el proxy del proveedor no cumpla alguna de las condiciones de arriba (por ejemplo, que almacene SSE en búfer). Entonces se vuelve a la opción 1 con un VPS limpio.
  - No cumplir RNF-16 o RNF-03 con un solo servidor ampliado.
  - Que el crecimiento exija varios servidores de aplicación.
  - Que, con el registro abierto, un despliegue rompa datos reales o un fallo solo aparezca en el servidor. Entonces se añade staging con alias propio en `kronoqr-app`.

## Verificación

- **CI:** Trivy sobre las imágenes y ShellCheck sobre los scripts de `deploy/`, sin hallazgos altos ni críticos.
- **Despliegue manual documentado** en `docs/operacion/`: se despliega una etiqueta concreta, se espera el health check y, si falla, se vuelve a la anterior. Se ensaya en local en el Bloque 10 y se prueba en producción en el Bloque 12.
- **Prueba de red:** desde un contenedor de `kronoqr-app` no se llega a `kapataz-db`, y `kapataz` resuelve a un solo contenedor.
- `tests/e2e_api/test_transporte.py` contra producción, tras el primer despliegue del Bloque 12 y antes de la 1.0.0: HTTP redirige a HTTPS, las respuestas llevan HSTS, el chat llega por SSE sin búfer y la api ve la IP real del cliente. `@pytest.mark.req("RNF-12")`.
- **Prueba unitaria del middleware de cabeceras:** toda respuesta lleva HSTS y las demás cabeceras de seguridad, también sin proxy delante. `@pytest.mark.req("RNF-12")`.
- **Escaneo externo de puertos:** solo responden 80 y 443 (los del proxy del proveedor); el 8000 y el 5432 no responden desde fuera. Resultado anotado en el PR del Bloque 12.
- **Simulacro de restauración** desde copia, con RPO y RTO medidos (RNF-15), documentado en `docs/operacion/`: en local en el Bloque 10 y en el servidor en la Parte II.
- **Prueba de carga** con k6 y la IA simulada (RNF-16): en local en el Bloque 10 y en producción en la Parte II.
