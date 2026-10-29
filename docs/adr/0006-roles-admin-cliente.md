# ADR-0006: Dos roles y un único usuario por empresa

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Las primeras versiones del plan preveían los roles `owner`, `admin` y `member`, con invitaciones y varios usuarios por empresa. Para el producto que se quiere lanzar esa complejidad no es necesaria.

## Decisión

- Solo existen dos roles:
  - **`admin`:** el equipo de la plataforma. Usa únicamente el panel interno (empresas, agente común, procesamiento, métricas). No pertenece a ninguna empresa (`tenant_id` nulo) y no usa la aplicación de las empresas.
  - **`cliente`:** el usuario de una empresa, con todos los permisos sobre los datos de su empresa.
- Cada empresa tiene **exactamente un usuario** con rol `cliente`, garantizado por una restricción única sobre `tenant_id` en `users`. No hay invitaciones ni miembros adicionales.
- El `admin` puede suspender y reactivar empresas, pero no puede ver tokens de Google ni contraseñas, y cualquier acceso a datos de una empresa por soporte requiere un motivo y queda auditado.

## Alternativas consideradas

- **owner / admin / member con invitaciones:** más flexible, pero añade gestión de miembros, permisos por rol y casos de prueba que hoy no aportan valor.

## Consecuencias

- La autorización dentro de una empresa se simplifica: si el usuario es el `cliente` de esa empresa, puede hacerlo todo.
- Si la empresa pierde el acceso de su único usuario, se recupera por email o, como último recurso, con una reasignación verificada por el `admin` y auditada.
- Añadir varios usuarios por empresa en el futuro exigirá un ADR nuevo y retirar la restricción única.
