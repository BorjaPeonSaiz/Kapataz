# ADR-002 — Python + FastAPI como backend

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-CO-01, RF-CO-07, RF-IN-03, RF-VO-02, RN-11, RNF-04

## Contexto

El backend de Kapataz hace dos cosas a la vez: un servicio web de facturación con reglas fiscales estrictas y un conjunto de piezas de IA que corren en nuestro servidor. Las piezas de IA del plan son librerías de Python: el SDK oficial `anthropic`, pdfplumber, Presidio con spaCy, fastembed y faster-whisper.

Además:

- El chat se emite por SSE y debe mostrar la primera respuesta en menos de 3 s (RNF-04).
- Las herramientas del agente y la extracción validan su entrada y su salida con esquemas (RF-IN-03, §4.6).
- El frontend genera su cliente tipado desde el contrato OpenAPI, así que el contrato debe salir del código.

La alternativa natural es Laravel, con herramientas equivalentes a las elegidas (Pint, PHPStan, Deptrac, Pest).

## Opciones consideradas

1. **Python 3.12 + FastAPI + Pydantic v2**
   - Ventajas: un solo lenguaje para la web y la IA; SDK oficial de Anthropic; Pydantic valida igual la API, los parámetros de las herramientas y la extracción; OpenAPI automático; async y SSE nativos.
   - Inconvenientes: pocas «baterías»: autenticación, administración y migraciones se montan aparte (ADR-025, Alembic); hay que cuidar la mezcla de código async y síncrono.
2. **Laravel (PHP)**
   - Ventajas: framework maduro con autenticación, colas y migraciones incluidas; ecosistema conocido.
   - Inconvenientes: las librerías de IA del plan son de Python, así que haría falta un segundo servicio en Python y dos stacks que mantener.
3. **Python + Django**
   - Ventajas: mismo ecosistema de IA; administración, ORM y migraciones incluidas.
   - Inconvenientes: el ORM empuja a poner la lógica en los modelos, en contra de ADR-001; OpenAPI y validación con Pydantic necesitan añadidos; soporte async menos directo.

## Decisión

Opción 1: Python 3.12 con FastAPI y Pydantic v2, con SQLAlchemy 2 y Alembic para la persistencia (ADR-004).

- FastAPI vive solo en `api/` (ADR-001). Los esquemas de la API son propios y no exponen entidades del dominio.
- El contrato OpenAPI se exporta a `docs/api/openapi.json` y se mantiene sincronizado con la implementación.
- Los errores siguen RFC 9457 (`application/problem+json`) con tipos estables.

## Consecuencias

- **Positivas**
  - Un solo stack para web, IA y pruebas (pytest, hypothesis, schemathesis).
  - El contrato tipado conecta backend y frontend sin tipos duplicados.
- **Negativas y mitigación**
  - Tipado opcional de Python → mypy `--strict` obligatorio en CI.
  - Autenticación propia → ADR-025, con revisión de `seguridad-ia`.
  - Llamadas bloqueantes (OCR, Whisper, embeddings) dentro de peticiones async → se ejecutan en el worker (ADR-026), no en el proceso de la API.
- **Qué haría reconsiderarla**
  - Que las piezas de IA dejen de depender de librerías de Python.
  - Que FastAPI deje de mantenerse o rompa la compatibilidad de forma reiterada.

## Verificación

- **CI:** ruff y mypy `--strict` en verde.
- **CI:** se regenera el contrato OpenAPI y se compara con `docs/api/openapi.json`; si difieren, falla.
- **Pruebas de contrato** con schemathesis en `tests/contract/` contra el OpenAPI, cada una con su marcador de requisito.
- **Prueba de streaming:** `tests/e2e_api/test_chat_sse.py` comprueba que `/api/chat` emite eventos SSE con `FakeLlm`, con `@pytest.mark.req("RF-CO-01")`.
- **import-linter:** `fastapi` solo se importa desde `kapataz.api` y `kapataz.main` (ADR-001).
