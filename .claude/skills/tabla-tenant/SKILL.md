---
name: tabla-tenant
description: Crea una migración de Laravel para una tabla de negocio con tenant_id, Row Level Security, claves foráneas compuestas, unicidad por empresa y su modelo con el scope de tenant y los tests de aislamiento. Úsala cada vez que haya que añadir una tabla con datos de una empresa (clientes, proveedores, facturas, documentos, etc.).
---

# Crear una tabla de negocio con aislamiento por empresa

Referencias: `docs/adr/0003-postgresql-pgvector.md`, `docs/adr/0005-aislamiento-multi-tenant.md` y la sección «Modelo de datos inicial» del plan. Antes de empezar, busca en `apps/web/database/migrations` una migración de tabla de negocio ya existente y sigue exactamente su patrón; si existe, prevalece sobre esta guía.

## Pasos

Sigue TDD (skill `tdd`): escribe primero los tests del paso 5 y comprueba que fallan; después crea la migración, el modelo, la política y la factory hasta que pasen.

1. **Migración** (`apps/web/database/migrations`), con:
   - `id`, `tenant_id` (`NOT NULL`, FK a `tenants`), columnas de negocio y `timestamps`.
   - Importes en `decimal` con precisión definida; moneda ISO en `char(3)`.
   - `UNIQUE (tenant_id, id)` para que otras tablas puedan referenciarla con clave compuesta.
   - Claves foráneas compuestas hacia otras tablas de negocio: `FOREIGN KEY (tenant_id, customer_id) REFERENCES customers (tenant_id, id)`.
   - Restricciones únicas de negocio con `tenant_id` delante (`UNIQUE (tenant_id, tax_id)`).
   - Índices para las consultas previstas, empezando por `tenant_id`.
   - RLS en SQL:
     ```sql
     ALTER TABLE <tabla> ENABLE ROW LEVEL SECURITY;
     ALTER TABLE <tabla> FORCE ROW LEVEL SECURITY;
     CREATE POLICY tenant_isolation ON <tabla>
       USING (tenant_id = current_setting('app.tenant_id')::bigint)
       WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
     ```
     Ajusta el tipo (`bigint` o `uuid`) al de `tenants.id`.
   - `down()` que deshace todo en orden inverso.
2. **Modelo** en el área de negocio que corresponda, usando el trait o scope global de tenant del proyecto, que rellena `tenant_id` desde la sesión y filtra todas las consultas. `tenant_id` no es asignable en masa.
3. **Política** de Laravel para el modelo: solo el usuario `cliente` de la misma empresa; `admin` no accede desde la aplicación de las empresas.
4. **Factory** que genere el registro dentro de un tenant dado.
5. **Tests** con dos empresas (Paco y Juan) y datos en ambas:
   - Paco no ve, no lista, no modifica y no borra registros de Juan (también con ID directo, que debe dar 404).
   - Un `INSERT` o `UPDATE` con el `tenant_id` de otra empresa falla por RLS.
   - La unicidad permite el mismo NIF o número en empresas distintas y lo impide en la misma.
6. **Ejecuta** las migraciones y los tests si el entorno está disponible e informa del resultado real.
7. Pasa la skill `revisar-aislamiento` sobre los ficheros creados.

Nombres de tabla y columnas en inglés y en plural snake_case.
