# ADR-0013: Logs JSON y trazas de LLM autoalojadas en la UE

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Hay que poder explicar por qué un documento terminó en revisión o falló, comparar versiones del agente, controlar el coste por empresa y cumplir el RGPD con datos contables y personales.

## Decisión

- Todos los servicios (Laravel, FastAPI y workers) emiten **logs JSON** con `trace_id`, `tenant_id`, `user_id`, `document_id` y `agent_version` cuando aplican (Monolog JSON en Laravel, structlog en Python), agregados en Loki/Grafana o equivalente.
- Las llamadas al LLM, a los embeddings y al reranker se registran como **trazas en Opik o Langfuse autoalojado en la UE**, con el mismo `trace_id`.
- El contenido de los documentos y los datos personales se enmascaran u omiten en logs y trazas; nunca se registran secretos ni tokens. Solo el rol `admin` accede a las trazas, con retención limitada.
- La suite de evaluación se ejecuta como experimento en Opik/Langfuse para comparar cada versión candidata del agente con la de producción.

## Alternativas consideradas

- **Servicio de trazas SaaS fuera de la UE:** descartado por privacidad.
- **Solo logs, sin trazas de LLM:** no permite evaluar ni comparar versiones del agente.

## Consecuencias

- Un servicio más que desplegar y mantener.
- El `trace_id` debe propagarse desde la petición web hasta el último job.
