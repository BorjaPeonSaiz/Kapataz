# ADR-0014: Servidor MCP después del MVP

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Algunos clientes querrán consultar sus datos desde asistentes externos como Claude, Cursor o Windsurf. Abrir ese canal antes de tener el aislamiento, los permisos y la auditoría probados en la aplicación añade riesgo.

## Decisión

- Después del MVP, el servicio FastAPI expondrá un **servidor MCP** con herramientas sobre los mismos servicios de dominio que usa el agente: `buscar_facturas`, `facturas_vencidas`, `resumen_cliente`, `resumen_proveedor` y `buscar_en_documentos`.
- Autenticación **OAuth 2.1 por usuario**, sin claves compartidas; el servidor aplica la empresa y el rol del usuario en cada llamada.
- Primera versión **de solo lectura**; las herramientas de escritura llegarán después con confirmación explícita.
- Rate limits por empresa, revocación de tokens y auditoría con `channel = mcp`.

## Alternativas consideradas

- **Incluir MCP en el MVP:** retrasa el lanzamiento y amplía la superficie de ataque antes de tiempo.

## Consecuencias

- Las tablas `oauth_clients` y `oauth_tokens` se crean en la Fase 6.
- Los tests de aislamiento entre empresas deben cubrir también este canal.
