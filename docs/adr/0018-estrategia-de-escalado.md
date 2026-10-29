# ADR-0018: Estrategia de escalado

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

El SaaS empieza con pocas empresas, pero debe poder llegar a miles sin rehacer la arquitectura ([ADR-0002](0002-arquitectura-laravel-fastapi.md), [ADR-0003](0003-postgresql-pgvector.md)). Cada empresa tiene un único usuario ([ADR-0006](0006-roles-admin-cliente.md)), así que la carga no la marca el número de usuarios, sino:

- el volumen de documentos subidos y procesados (OCR, extracción, embeddings, archivado en Drive);
- las consultas al agente (LLM, búsqueda híbrida y reranking);
- el tamaño de las tablas de negocio y de `document_chunks`.

Escalar antes de tiempo añade coste y complejidad; no prepararse obliga a migraciones difíciles después. Esta decisión fija qué se deja preparado desde el principio y qué se activa solo al alcanzar umbrales medidos.

## Decisión

### Desde la Fase 1 (obligatorio)

1. **Servicios sin estado.** `app`, `agent` y los workers no guardan nada en disco local ni en memoria entre peticiones: sesiones, caché, colas y bloqueos en Redis; ficheros en S3 y Drive. Cualquier servicio se puede replicar detrás del balanceador sin cambios.
2. **Contexto de empresa por transacción.** El `tenant_id` se fija con `SET LOCAL app.tenant_id` (o `set_config(..., true)`) al inicio de **cada transacción**, nunca a nivel de sesión o conexión. Así RLS sigue siendo correcto cuando se añada un gestor de conexiones en modo transacción (PgBouncer) y una conexión reutilizada no puede arrastrar la empresa de la petición anterior. Hay un test que lo comprueba.
3. **Todo lo pesado va por colas.** OCR, extracción, embeddings, archivado en Drive y reintentos se ejecutan en workers, nunca en la petición web. Colas separadas por tipo de trabajo (`ingest`, `index`, `drive`, `agent`) y reparto equitativo por empresa, para que una carga masiva de una empresa no retrase a las demás.
4. **Límites por empresa** configurables por el `admin`: documentos por día, tamaño máximo, consultas al agente por hora y coste mensual de IA. Al superarlos se avisa al usuario en lugar de fallar en silencio.
5. **Índices que empiezan por `tenant_id`** en todas las consultas frecuentes y paginación por cursor en los listados grandes.
6. **Métricas de capacidad** desde el principio (Fase 1 y Fase 3): latencia p95 por endpoint, profundidad y antigüedad de cada cola, duración de la ingesta, conexiones a PostgreSQL, tamaño de tablas e índices, errores y cuota de la API de Drive, y coste y tokens de IA por empresa.

### Al alcanzar umbrales (se activa con datos, no antes)

Los umbrales son orientativos: se revisan con pruebas de carga antes de abrir el registro (Fase 5) y con las métricas reales de producción.

| Señal medida | Umbral orientativo | Acción |
| --- | --- | --- |
| Profundidad o antigüedad de las colas de ingesta | Trabajos esperando más de 5 minutos de forma sostenida | Más réplicas de `worker` y autoescalado por longitud de cola |
| Workers de Laravel ocupados esperando la extracción síncrona ([ADR-0015](0015-python-extrae-laravel-persiste.md)) | Más del 50 % del tiempo de los workers en espera | Pasar la extracción a modo asíncrono: Python devuelve el resultado por cola y Laravel lo consume |
| Conexiones a PostgreSQL | Más del 70 % de `max_connections` | PgBouncer en modo transacción (posible gracias al punto 2) |
| CPU o lecturas en PostgreSQL | CPU por encima del 70 % sostenido, o consultas del agente y del panel compitiendo con la ingesta | Réplica de lectura para las herramientas de solo lectura del agente, el panel de `admin` y las métricas |
| Tamaño de `document_chunks` | Del orden de 5-10 millones de filas, o p95 de la búsqueda híbrida por encima de 500 ms | Particionar `document_chunks` por hash de `tenant_id` y ajustar los parámetros de HNSW |
| Búsqueda vectorial todavía lenta tras particionar | p95 por encima de 500 ms sostenido | Mover los vectores a una base vectorial dedicada con filtro obligatorio por empresa, sin migrar los datos transaccionales ([ADR-0003](0003-postgresql-pgvector.md)) |
| Tablas de negocio grandes (`documents`, `invoices`, `audit_log`) | Decenas de millones de filas o mantenimiento (`VACUUM`, índices) que degrada el servicio | Particionar `audit_log` por fecha y las tablas grandes por `tenant_id` |
| Cuota de la API de Google Drive | Errores 403/429 de cuota en más del 1 % de las llamadas | Ajustar el reparto por empresa y la espera exponencial, y solicitar más cuota a Google |
| Coste de IA por empresa | Por encima del margen del plan de precios | Caché de respuestas y embeddings, modelos más baratos para clasificación, revisión de límites y precios |

### Lo que no se hace

- **No se divide en microservicios** por volumen: la división entre `apps/web` y `apps/agent` se mantiene; se escala replicando servicios, no partiéndolos.
- **No se crea una base de datos por empresa** salvo que un cliente lo exija por contrato; en ese caso será un ADR propio.
- **No se escala por adelantado:** cada acción de la segunda tabla se activa con una métrica que la justifique y se registra en el registro de cambios del README.

## Alternativas consideradas

- **Diseñar desde el inicio para escala máxima** (microservicios, base vectorial dedicada, base de datos por empresa): mucho más coste de construcción y operación sin clientes que lo justifiquen.
- **No preparar nada y resolverlo cuando llegue:** cambiar después el contexto de empresa o sacar trabajos de la petición web obliga a tocar todo el código de acceso a datos.

## Consecuencias

- Lo obligatorio desde la Fase 1 (servicios sin estado, `SET LOCAL`, colas, límites, índices y métricas) apenas añade trabajo si se hace desde el principio.
- Las pruebas de carga pasan a formar parte de la Fase 5.
- Los cuellos de botella esperables a corto plazo son el coste y los límites de los proveedores de IA y las cuotas de Google Drive, no la web ni la base de datos.
- Cada acción de escalado que se active se documenta con la métrica que la motivó.
