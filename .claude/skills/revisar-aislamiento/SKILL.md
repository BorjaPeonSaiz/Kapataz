---
name: revisar-aislamiento
description: Revisa un cambio, una funcionalidad o un fichero para comprobar que una empresa no puede ver ni modificar datos de otra (escenario Paco, Juan y Alberto). Úsala antes de dar por terminada cualquier tarea que toque modelos, consultas, endpoints, jobs, el RAG, herramientas del agente, Google Drive o MCP.
---

# Revisión de aislamiento entre empresas

Referencia: `docs/adr/0005-aislamiento-multi-tenant.md`. Escenario: Paco y Juan son dos empresas; ambas tienen a Alberto como cliente (mismo NIF). Paco nunca debe ver, modificar ni deducir nada de los datos de Juan.

## Qué revisar

Identifica los ficheros del cambio (por ejemplo, con `git diff --name-only` o lo que indique el usuario) y comprueba cada punto que aplique:

**Datos**
- [ ] Las tablas nuevas tienen `tenant_id NOT NULL`, política RLS con `USING` y `WITH CHECK`, y `FORCE ROW LEVEL SECURITY`.
- [ ] Las claves foráneas entre tablas de negocio son compuestas `(tenant_id, id)`.
- [ ] Las restricciones únicas incluyen `tenant_id` (NIF, números de factura o presupuesto).
- [ ] La deduplicación de clientes y proveedores solo busca dentro del tenant.

**Código**
- [ ] El `tenant_id` sale de la sesión o del contexto del job, nunca de la petición HTTP, de un formulario ni de un argumento del modelo de IA.
- [ ] Ninguna consulta usa `withoutGlobalScopes`, SQL crudo sin filtro de tenant ni conexión con `BYPASSRLS`.
- [ ] Las rutas con IDs (`/invoices/{id}`) cargan el registro dentro del tenant y aplican la política; un ID de otra empresa devuelve 404, no 403.
- [ ] Jobs y colas llevan `tenant_id` y lo fijan (`app.tenant_id`) antes de tocar la base de datos.
- [ ] Las claves de caché llevan prefijo de tenant.

**Agente, RAG, Drive y MCP**
- [ ] Las herramientas del agente reciben el `tenant_id` del servidor; el esquema de la herramienta no lo expone al modelo.
- [ ] La búsqueda vectorial y textual filtra por `tenant_id` dentro de la consulta.
- [ ] Las respuestas no revelan la existencia de datos de otras empresas.
- [ ] Las operaciones de Drive usan el token y las carpetas de la empresa de la sesión.
- [ ] Las herramientas MCP aplican el tenant del usuario autenticado.

**Tests**
- [ ] Hay tests con dos empresas y un cliente compartido que prueban la nueva vía: lectura, listado, búsqueda, modificación y borrado con IDs de la otra empresa.

## Resultado

Devuelve una tabla con cada punto aplicable (cumple / no cumple / no aplica), y para cada «no cumple»: fichero y línea, cómo se explotaría y la corrección. Si todo cumple, dilo y enumera lo revisado. Para una revisión más profunda, delega en el agente `seguridad`.
