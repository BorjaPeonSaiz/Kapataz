# ADR-014 — Despliegue con Docker Compose en un VPS de la UE

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RNF-01, RNF-03, RNF-12, RNF-14, RNF-15, RNF-16
- **Se cierra en:** Bloque 10

## Contexto

Kapataz necesita en producción varios procesos permanentes:

- **api:** FastAPI, que también sirve el frontend (ADR-013).
- **worker:** cola de tareas para ingesta, embeddings y transcripción (ADR-026).
- **PostgreSQL** con pgvector (ADR-004).
- **Caddy** como proxy con TLS automático.

Requisitos:

- Datos en servidores de la UE (RNF-01).
- Disponibilidad del 99,5 % mensual (RNF-03).
- Solo HTTPS con HSTS; base de datos y servicios internos sin exponer (RNF-12).
- Copias cifradas fuera del servidor, en la UE, con RPO ≤ 15 min y RTO ≤ 4 h (RNF-15).
- 100 cuentas activas a la vez sin incumplir RNF-04 (RNF-16).

Lo opera una sola persona, con entornos separados de staging y producción.

## Opciones consideradas

1. **Docker Compose en un VPS de la UE, con Caddy**
   - Ventajas: sencillo de operar y de reproducir en local; mismo Compose en desarrollo y en el servidor; TLS automático.
   - Inconvenientes: un solo servidor es un punto único de fallo; se escala en vertical.
2. **Hosting compartido de webs y WordPress**
   - Ventajas: barato.
   - Inconvenientes: no ejecuta procesos Python permanentes, PostgreSQL ni Whisper. Descartado.
3. **Kubernetes, gestionado o propio**
   - Ventajas: escalado y despliegues graduales.
   - Inconvenientes: complejidad de operación desproporcionada para una persona y para la carga de RNF-16.
4. **Plataforma gestionada de contenedores con base de datos gestionada**
   - Ventajas: menos operación propia.
   - Inconvenientes: hay que encontrar región en la UE, soporte de pgvector y un worker con CPU suficiente para Whisper; menos control sobre copias y red.

## Decisión

Opción 1.

- **Compose** con api, worker, PostgreSQL y Caddy. Solo Caddy se expone a internet.
- **Imágenes:** Dockerfile multietapa sin root, fijadas por digest (ADR-022). Se identifican por commit hasta la 1.0.0 y por versión desde entonces (ADR-032).
- **Despliegue:** migraciones controladas, health checks reales (`/api/health` comprueba base de datos y API de Claude por separado) y vuelta atrás probada. Una migración irreversible se despliega en dos pasos compatibles.
- **Secretos** fuera del repositorio y de las imágenes, incluida la clave de la API de Claude.
- **Copias** cifradas fuera del servidor, en la UE, con archivado de WAL y simulacros de restauración.
- **Cada cambio se prueba en staging** antes de producción.

El Bloque 10 cierra este ADR con producción, copias, observabilidad y prueba de carga hechas.

## Consecuencias

- **Positivas**
  - Infraestructura que entiende y opera una persona.
  - El entorno de desarrollo es el mismo Compose.
- **Negativas y mitigación**
  - Punto único de fallo → RNF-03 admite unas 3,6 horas de caída al mes; monitor externo de disponibilidad, alertas con runbook y restauración probada dentro del RTO de 4 h.
  - CPU compartida entre API, OCR, embeddings y Whisper → todo lo pesado va al worker con concurrencia limitada; RNF-14 y RNF-16 medidos.
  - Despliegue fallido → la versión anterior sigue funcionando y la vuelta atrás está probada.
- **Qué haría reconsiderarla**
  - No cumplir RNF-16 o RNF-03 con un solo servidor ampliado.
  - Que el crecimiento exija varios servidores de aplicación.

## Verificación

- **CI:** Trivy sobre las imágenes y ShellCheck sobre los scripts de `deploy/`, sin hallazgos altos ni críticos.
- **Workflow `deploy.yml`:** despliega en staging, espera el health check y vuelve atrás si falla.
- `tests/e2e_api/test_transporte.py` contra staging: HTTP redirige a HTTPS y las respuestas llevan HSTS. `@pytest.mark.req("RNF-12")`.
- **Escaneo externo de puertos:** solo responden 80 y 443. Resultado anotado en el PR del Bloque 10.
- **Simulacro de restauración** desde copia, con RPO y RTO medidos (RNF-15), documentado en `docs/operacion/`.
- **Prueba de carga** con k6 y la IA simulada (RNF-16).
