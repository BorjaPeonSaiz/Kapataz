# ADR-0015: Python extrae y devuelve los datos; Laravel los guarda

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

[ADR-0002](0002-arquitectura-laravel-fastapi.md) reparte el sistema entre Laravel (`apps/web`) y FastAPI (`apps/agent`), y establece que cada regla de negocio vive en un único servicio de dominio. Sin embargo, el plan hacía que el worker de Python guardara directamente las facturas, los presupuestos y los clientes o proveedores extraídos. Con dos aplicaciones escribiendo los mismos datos, reglas como la deduplicación por NIF dentro de la empresa ([ADR-0005](0005-aislamiento-multi-tenant.md)), el bloqueo de documentos enviados ([ADR-0011](0011-bloqueo-documentos-enviados.md)), la numeración o la auditoría acabarían duplicadas en PHP y en Python, y tarde o temprano divergirían.

## Decisión

- **Laravel es el único que escribe los datos de negocio**: clientes, proveedores, facturas, presupuestos, líneas, estado de los documentos y auditoría. Lo hace siempre con sus servicios de dominio, los mismos que usa el CRUD manual.
- **Python extrae y devuelve.** El servicio de FastAPI recibe la referencia del documento, lee la copia privada de S3, hace OCR, extracción y clasificación, y devuelve un resultado estructurado y validado con Pydantic (tipo, dirección, emisor, receptor, cabecera, líneas, impuestos, totales, confianza por campo, tipo sugerido y resumen). No escribe tablas de negocio.
- **Python solo escribe sus propias tablas**: `document_chunks` (fragmentos y embeddings), `conversations` y `messages` del agente, siempre con `tenant_id` y RLS.
- **Lectura.** Las herramientas de solo lectura del agente leen los datos de negocio con un rol de base de datos de solo lectura, sujeto a RLS y con el `tenant_id` fijado por el servidor. Cualquier escritura que inicie el agente (siempre con confirmación del usuario) se hace llamando a la API interna de Laravel.
- **Orquestación desde Laravel.** Un job de Horizon por documento encadena los pasos:
  1. Pide a FastAPI la extracción (`POST /internal/documents/{id}/extract`).
  2. Valida de nuevo el resultado y lo guarda con los servicios de dominio en una transacción: normalización, deduplicación, alta o enlace de cliente/proveedor, factura o presupuesto con sus líneas, y estado del documento.
  3. Pide a FastAPI la indexación (`POST /internal/documents/{id}/index`), que crea los fragmentos y embeddings.
  4. Pide a FastAPI el archivado en Google Drive en la carpeta que corresponda.

  Cada paso es idempotente y se reintenta por separado, sin repetir los anteriores.
- **Contrato.** Los esquemas Pydantic de FastAPI (publicados como OpenAPI) son el contrato entre las dos aplicaciones. Hay tests de contrato en ambos lados.
- **Llamadas internas.** Solo dentro de la red privada, autenticadas con un secreto interno, con `tenant_id` y `trace_id` en cada petición y tiempos de espera amplios para la extracción (por ejemplo, 120 segundos).

## Alternativas consideradas

- **Python escribe todo lo que extrae:** obliga a reimplementar en Python las reglas de negocio de Laravel o a saltárselas.
- **Python devuelve el resultado mediante una cola y Laravel lo consume:** más desacoplado, pero añade complejidad que el volumen del MVP no necesita. Se puede adoptar más adelante sin cambiar el reparto de responsabilidades.
- **Mover la extracción a PHP:** el ecosistema de OCR, extracción e IA es mucho más pobre en PHP.

## Consecuencias

- Una sola implementación de cada regla de negocio, compartida por el CRUD manual, la ingesta, la opción «Es factura / Es presupuesto / Es proveedor» de «Por clasificar» y las escrituras del agente.
- Python no necesita permisos de escritura sobre las tablas de negocio: su rol de base de datos solo escribe en sus tablas.
- Hay que mantener el contrato entre las dos aplicaciones y versionarlo cuando cambie.
- La extracción añade una llamada interna con su tiempo de espera; se mide en las trazas.
