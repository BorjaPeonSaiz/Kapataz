# ADR-0005: Aislamiento total entre empresas

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Es un requisito crítico que una empresa nunca vea datos de otra, aunque compartan clientes o proveedores. Ejemplo de referencia: Paco y Juan son dos empresas y las dos tienen a Alberto como cliente. Si Paco pide las facturas de Alberto, solo debe ver las que él emitió, nunca las de Juan, ni saber que Alberto es cliente de Juan.

## Decisión

1. **Registros por empresa.** No hay fichas globales de clientes ni de proveedores. Alberto existe una vez por cada empresa, y la deduplicación por NIF/CIF solo compara dentro de la misma empresa (`UNIQUE (tenant_id, tax_id)`).
2. **El tenant sale de la sesión.** El `tenant_id` lo fija el servidor a partir del usuario autenticado y se inyecta en todas las herramientas del agente. El modelo nunca lo recibe ni lo elige.
3. **Row Level Security** en todas las tablas de negocio, con `app.tenant_id` fijado en cada transacción, y claves foráneas compuestas `(tenant_id, id)`.
4. **RAG filtrado dentro de la consulta**, antes de buscar, no después.
5. **Google Drive separado** por empresa, con su propia cuenta y su propio token.
6. **Contexto del agente separado:** conversaciones, cachés, colas y trazas por empresa.
7. **Respuestas sin pistas:** lo que no pertenece a la empresa se responde como «no encontrado».
8. **Acceso de soporte del `admin`** solo con motivo y auditado, y nunca a través del agente.

## Alternativas consideradas

- **Filtrar solo en la capa de aplicación:** un olvido en una consulta expondría datos; RLS añade una segunda barrera en la base de datos.
- **Una base de datos por empresa:** aislamiento fuerte, pero mucho más coste operativo y de migraciones para el volumen previsto.

## Consecuencias

- La suite de tests incluye obligatoriamente el escenario Paco, Juan y Alberto por todas las vías (API, CRUD, búsqueda, chat, RAG, Drive y MCP), además de intentos explícitos de saltarse el aislamiento. Un fallo bloquea el despliegue.
- Los datos de terceros compartidos se duplican entre empresas, lo cual es intencionado.
