# ADR-0002: Laravel para la web y FastAPI para el agente y la ingesta

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

El producto combina una aplicación SaaS clásica (autenticación, CRUD, permisos, colas, pagos) con procesamiento de documentos e IA (OCR, extracción, embeddings, RAG, LLM). El ecosistema de IA y de procesamiento de documentos es mucho más maduro en Python.

## Decisión

- **Laravel 12 + Inertia.js + Vue 3 + TypeScript + Tailwind** para la web, la API, el CRUD, la autenticación, los permisos, las colas (Horizon), el scheduler y el panel de administración.
- **Python 3.12 + FastAPI** para la ingesta, la extracción, la clasificación, los embeddings, el RAG, el runtime del agente común, la integración con Google Drive y, después del MVP, el servidor MCP.
- Monorepo con `apps/web` y `apps/agent`, Docker Compose para el entorno local y GitHub Actions para CI.
- Las dos aplicaciones comparten la base de datos PostgreSQL y Redis, y se comunican por endpoints internos en red privada. Los servicios de dominio (reglas de negocio) son la única vía de escritura, tanto para el CRUD manual como para la ingesta.

## Alternativas consideradas

- **Todo en Laravel:** las librerías de OCR, extracción tabular, embeddings y rerankers en PHP son escasas.
- **Todo en Python (Django o FastAPI con frontend aparte):** viable, pero se pierde la productividad de Laravel para el SaaS (Cashier, Horizon, políticas, Inertia).
- **Streamlit para la interfaz:** descartado; la interfaz de clientes y la de administración se hacen con Laravel + Inertia + Vue, y las evaluaciones se revisan en Opik/Langfuse.

## Consecuencias

- Dos lenguajes y dos suites de tests en el mismo repositorio.
- Hay que propagar `trace_id` y `tenant_id` entre Laravel, FastAPI y workers.
- Hay que evitar duplicar reglas de negocio entre las dos aplicaciones: cada regla vive en un único servicio de dominio.
