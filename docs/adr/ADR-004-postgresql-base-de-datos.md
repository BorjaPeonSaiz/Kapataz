# ADR-004 — PostgreSQL como base de datos

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-FA-02, RF-AC-05, RN-10, RN-F-01, RN-F-02, RN-F-04, RN-F-07, RNF-13, RNF-15, RNF-16

## Contexto

Kapataz es un servicio web con muchas cuentas a la vez. La base de datos tiene que garantizar cosas que el código solo no puede garantizar:

- **Numeración sin huecos** por cuenta, serie y año, aunque se emitan varias facturas a la vez (RN-F-01). Exige bloqueo de fila en la misma transacción que la emisión.
- **Una sola cadena de registros por cuenta** que no se bifurca, aunque se emitan a la vez facturas de series distintas (RN-F-07). Exige bloquear también la cabeza de la cadena.
- **Inmutabilidad** de la factura emitida también ante SQL directo (RN-F-02). Exige triggers.
- **Aislamiento entre cuentas** en la propia base de datos (RNF-13, ADR-024). Exige seguridad a nivel de fila y roles.
- **Copias** con RPO ≤ 15 min y RTO ≤ 4 h (RNF-15). Exige archivado continuo del registro de transacciones.

Además, otras decisiones se apoyan en la misma base de datos: la búsqueda de texto y vectorial (ADR-007) y la cola de tareas (ADR-026).

## Opciones consideradas

1. **PostgreSQL + SQLAlchemy 2 + Alembic**
   - Ventajas: `SELECT … FOR UPDATE`, triggers, Row Level Security y roles sin `BYPASSRLS`; archivado de WAL; búsqueda de texto en español con `unaccent`; extensión pgvector; cola con procrastinate sin Redis.
   - Inconvenientes: hay que operarla (copias, actualizaciones, extensiones); las pruebas de integración necesitan un PostgreSQL real.
2. **SQLite**
   - Ventajas: cero operación; un fichero.
   - Inconvenientes: un solo escritor a la vez; sin RLS ni roles; copias continuas con RPO de minutos más difíciles; la búsqueda vectorial y la cola irían aparte.
3. **MySQL o MariaDB**
   - Ventajas: muy extendidas; bloqueo de fila y triggers.
   - Inconvenientes: sin seguridad a nivel de fila nativa, así que el aislamiento dependería solo del código (en contra de RNF-13); la búsqueda vectorial y la cola necesitarían otros servicios.

## Decisión

Opción 1. Una base de datos PostgreSQL compartida por todas las cuentas, con SQLAlchemy 2 (estilo 2.0, tipado) y migraciones Alembic reversibles.

- Toda operación que añade un registro de facturación bloquea con `SELECT … FOR UPDATE`, en la misma transacción, primero la cabeza de la cadena de la cuenta (`billing_chain_heads`, una fila por cuenta) y después el contador de la serie (`series_counters`), siempre en ese orden (RN-F-07). Así, dos emisiones simultáneas no enlazan con el mismo registro anterior aunque sean de series distintas.
- RN-F-04 (fecha no anterior a la última de la serie) se comprueba con el contador ya bloqueado, para que una emisión simultánea no pueda colarse entre la comprobación y el número.
- Un trigger impide `UPDATE` y `DELETE` de los campos fiscales con `status='issued'`.
- Toda tabla de negocio lleva `tenant_id` y política RLS. La aplicación se conecta con un rol sin `BYPASSRLS` y fija la cuenta en cada transacción, también en el worker (ADR-024). Las tablas globales que se leen antes de conocer la cuenta van sin RLS, en una lista cerrada (ADR-024).
- Extensiones: pgvector y `unaccent`.
- Copias cifradas fuera del servidor, en la UE, con archivado de WAL (RNF-15).
- La base de datos no se expone a internet (RNF-12, ADR-014).

## Consecuencias

- **Positivas**
  - Las garantías fiscales y de aislamiento no dependen solo del código.
  - Un único almacén para datos, búsqueda y cola: menos servicios que operar y copiar.
- **Negativas y mitigación**
  - Coste de operación → imagen fijada por digest (ADR-022), runbooks en `docs/operacion/` y simulacro de restauración en el Bloque 10.
  - Pruebas más lentas que con una base en memoria → las unitarias de dominio no usan base de datos (ADR-001); solo las de integración usan PostgreSQL real.
  - RLS mal configurada en una tabla nueva → prueba que recorre todas las tablas de negocio (ver Verificación).
- **Qué haría reconsiderarla**
  - Que RLS impida cumplir RNF-16 con 100 cuentas a la vez.
  - Que el alojamiento en la UE elegido no admita las extensiones necesarias.

## Verificación

- **CI** ejecuta las pruebas de integración contra un PostgreSQL real.
- `tests/integration/billing/test_numeracion_concurrente.py`: 20 emisiones en paralelo con procesos distintos, en una cuenta y en varias; ni huecos ni duplicados. `@pytest.mark.req("RN-F-01")`. También emisiones simultáneas de las series F y R en la misma cuenta: la cadena de registros no se bifurca. `@pytest.mark.req("RN-F-07")`.
- `tests/integration/billing/test_inmutabilidad_sql.py`: un `UPDATE` por SQL directo sobre una factura emitida falla por el trigger. `@pytest.mark.req("RN-F-02")`.
- `tests/integration/test_rls.py`: con el rol de la aplicación, una consulta sin cuenta fijada no devuelve filas, la cuenta A no ve datos de la B y toda tabla de negocio tiene política RLS; falla si aparece una tabla sin RLS fuera de la lista cerrada de tablas globales. `@pytest.mark.req("RNF-13")`.
- Cada migración Alembic se prueba con `upgrade` y `downgrade` en CI.
- Restauración desde copia probada en el Bloque 10, con RPO y RTO medidos (RNF-15).
