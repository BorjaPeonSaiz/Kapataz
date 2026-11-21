# ADR-024 — Multitenencia con Row Level Security

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Modificado:** 2026-11-17. Borja confirma `email_verifications` en la lista cerrada de tablas globales sin RLS.
- **Modificado:** 2026-11-20. Al cerrar el Bloque 3, Borja aprueba cómo se da de alta el espacio de demostración bajo RLS (migración 0004, ver «Espacio de demostración bajo RLS»).
- **Modificado:** 2026-11-21. Borja aprueba las correcciones de la segunda revisión de seguridad: la carga desde la API solo para la cuenta de la sesión (S3-R-03) y la revisión de las filas existentes antes de la migración 0004 (S3-R-05).
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-10, RNF-13, RF-AC-05, RF-CF-04, RN-13, RF-SA-05

## Contexto

Kapataz es un servicio multiusuario: muchos autónomos comparten servidor y base de datos. Que una cuenta vea facturas, clientes o NIF de otra es el riesgo principal del producto (OWASP A01, LLM02, LLM08).

RN-10 prohíbe que una consulta, herramienta o tarea en segundo plano acceda a datos de otra cuenta. RNF-13 exige que el aislamiento se haga cumplir en la base de datos, además de en el código. El acceso a datos llega por muchos caminos: endpoints, herramientas del agente, búsqueda híbrida, tareas del worker y exportaciones. Un filtro olvidado en uno solo basta para una fuga.

La v1 tiene un usuario por cuenta, pero el modelo separa `tenant_id` y `user_id` para admitir equipos más adelante (§1.4).

## Opciones consideradas

1. **Una base de datos por cuenta.**
   - Ventajas: aislamiento fuerte y borrado sencillo.
   - Inconvenientes: migraciones, copias y conexiones multiplicadas por cuenta; inviable de operar para una persona en un VPS.
2. **Un esquema de PostgreSQL por cuenta.**
   - Ventajas: aislamiento razonable en una sola base.
   - Inconvenientes: migraciones por esquema, catálogo que crece con cada cuenta, y búsqueda y agregados de plataforma más complejos.
3. **Base compartida con `tenant_id` filtrado solo en el código.**
   - Ventajas: sencilla y habitual.
   - Inconvenientes: un `WHERE` olvidado expone datos; incumple RNF-13.
4. **Base compartida con `tenant_id` en toda tabla de negocio y políticas RLS.**
   - Ventajas: el aislamiento lo garantiza PostgreSQL aunque el código falle; una sola migración y una sola copia.
   - Inconvenientes: hay que fijar la cuenta en cada transacción y probar que nunca se arrastra; las políticas añaden algo de coste a las consultas.

## Decisión

Se elige la opción 4.

- Toda tabla de negocio lleva `tenant_id` y una política RLS que filtra por la cuenta fijada.
- La aplicación se conecta con un rol sin `BYPASSRLS` y que no es propietario de las tablas. Las migraciones usan otro rol.
- La cuenta se fija en cada transacción, con alcance de transacción, para que una conexión reutilizada del pool no arrastre la cuenta anterior.
- Sin cuenta fijada, una consulta no devuelve filas.
- El código también filtra por cuenta: RLS es la segunda barrera, no la única.
- Las tareas del worker llevan su `tenant_id` y fijan la cuenta igual que una petición (ADR-026).
- `chunks` tiene RLS: la búsqueda híbrida no puede devolver fragmentos de otra cuenta. Ninguna caché ni el prompt caching mezclan cuentas.
- Un identificador de otra cuenta responde 404, nunca 403.
- El espacio de demostración es un tipo de cuenta: `tenants.kind` vale `demo` y `parent_tenant_id` guarda la cuenta a la que pertenece. Su borrado lo hace una función de mantenimiento que solo actúa sobre ese tipo de cuenta. Cómo se da de alta sin abrir RLS, en «Espacio de demostración bajo RLS».
- **Tablas globales sin RLS, en una lista cerrada.** Algunas tablas se leen antes de saber de qué cuenta se trata: al iniciar sesión, al validar la cookie o al recibir un webhook de Stripe. Esas tablas no llevan RLS: `users`, `sessions`, `email_verifications`, `subscriptions`, `payment_events` y las de plataforma (`platform_settings`, `platform_admins`, `platform_audit_events`). Solo las consulta un repositorio de cuentas acotado.
- Las tablas de plataforma no son de una cuenta y solo las escribe el superadministrador (ADR-031), que no lee datos de negocio (RF-SA-05).
- **Agregados del superadministrador** (como el coste por cuenta): salen de funciones `SECURITY DEFINER` que solo devuelven metadatos y agregados (RF-SA-05). Así el rol de la aplicación no necesita `BYPASSRLS`.

## Consecuencias

- **Positivas:**
  - Una consulta mal escrita no cruza datos entre cuentas.
  - Una sola base que migrar, copiar y restaurar (ADR-004).
  - Preparado para varios usuarios por cuenta sin cambiar el modelo.
- **Negativas y mitigación:**
  - Coste de rendimiento de las políticas. Se mitiga con índices que empiezan por `tenant_id` y se mide con `EXPLAIN`.
  - Riesgo de fijar mal la cuenta en el pool. Se mitiga con alcance de transacción y una prueba específica.
  - Los agregados de plataforma (coste por cuenta) necesitan otro camino de lectura. Se resuelve con funciones `SECURITY DEFINER` que solo devuelven metadatos y agregados, sin dar al superadministrador acceso a datos de negocio (ADR-031).
  - Las tablas globales quedan fuera de RLS. Se mitiga con una lista cerrada, un único repositorio de cuentas que las consulta y una prueba que falla si aparece otra tabla sin RLS.
- **Qué haría reconsiderarla:** clientes que exijan aislamiento físico por contrato, o un volumen que obligue a repartir cuentas entre varias bases.

## Verificación

- `test_a01_rls_sin_cuenta_sin_filas`: con el rol de la aplicación, una consulta sin cuenta fijada no devuelve filas (`@pytest.mark.req("RNF-13")`, `owasp("A01")`).
- Prueba de que toda tabla de negocio tiene `tenant_id` y política RLS: recorre el catálogo de PostgreSQL y falla si aparece una tabla sin RLS que no esté en la lista cerrada de tablas globales (`req("RNF-13")`).
- Prueba de que el rol de la aplicación no tiene `BYPASSRLS` ni es propietario de las tablas.
- Prueba del pool: una conexión reutilizada no conserva la cuenta anterior.
- `test_a01_idor_todas_las_rutas`: prueba parametrizada sobre `openapi.json` que llama a cada ruta con recursos de otra cuenta y espera 404 (`req("RN-10")`).
- `test_llm08_otra_cuenta_no_aparece` y escenario «Aislamiento entre cuentas».
- Prueba del worker: cada tarea corre en el contexto de su cuenta.
- Espacio de demostración (migración 0004): `tests/integration/persistence/test_espacio_demo_sql.py` (alta desde la cuenta fijada; padre ajeno e inexistente con el mismo error; ni demo dentro de demo, ni dos espacios por cuenta, ni cambios de `id`, `kind` o `parent_tenant_id`, tampoco para el propietario; la app solo actualiza `name`), `tests/integration/test_migrations.py::test_la_0004_se_deshace_y_se_rehace` y el id derivado en `tests/unit/domain/test_accounts.py` (`req("RF-CF-04")`, `req("RN-10")`, `req("RNF-13")`).
- import-linter: `kapataz.api` no importa `kapataz.application.use_cases.admin` ni, directamente, `kapataz.application.use_cases.demo_space_loader` (`backend/pyproject.toml`, S3-R-03).
- Carga desde la sesión: `LoadDemoSpace` crea siempre el espacio de la cuenta del usuario, y las variantes por email y por id hacen lo mismo con el mismo núcleo (`tests/unit/application/test_load_demo_space.py` y, contra PostgreSQL, `tests/integration/persistence/test_seed_demo.py::test_desde_la_sesion_carga_el_espacio_de_la_cuenta_del_usuario`; `req("RF-CF-04")`, `req("RN-10")`).
- La 0004 no se aplica sobre filas que la incumplen, y su error no lleva ids (`tests/integration/test_migrations.py::test_la_0004_no_se_aplica_si_hay_filas_que_la_incumplen`, `req("RF-CF-04")`).

## Espacio de demostración bajo RLS

Añadido al cerrar el Bloque 3 (20/11/2026). Detalle en el docstring de `backend/alembic/versions/20261120_0004_espacio_de_demostracion.py`.

**Problema.** RLS solo deja ver la fila de `tenants` de la cuenta fijada. El espacio tiene otro id, así que desde su cuenta padre no se puede ni buscar ni insertar con `tenant_isolation`.

**Id derivado.** El id del espacio es `uuid5(espacio de nombres fijo, id de la cuenta)` (`demo_tenant_id` en `domain/accounts/model.py`): la cuenta padre lo calcula sin leer la fila. La base de datos no lo exige: UUIDv5 usa SHA-1, que PostgreSQL no trae de serie (solo `md5` y la familia SHA-2), y `pgcrypto` o `uuid-ossp` son extensiones que el despliegue no garantiza. Lo que sí exige es un espacio por cuenta, con el índice único `uq_tenants_parent_tenant_id`: si un fallo diera de alta un espacio con otro id, la cuenta no lo encontraría y tampoco podría crear el bueno.

**Migración 0004:**

- **Antes de nada, revisa las filas que ya hay** (S3-R-05). El trigger no revisa las existentes y el índice único fallaría con un `DETAIL` que lleva el id repetido. Por eso, antes de crear el índice y el trigger, bloquea `tenants` con `LOCK TABLE public.tenants IN SHARE ROW EXCLUSIVE MODE` hasta el final de la migración, para que nadie escriba entre la comprobación y el trigger. Un bloque `DO` cuenta los espacios sin cuenta padre, los que cuelgan de una cuenta que no es `standard` y las cuentas con más de un espacio. Si alguno no es cero, lanza `KZF14` con un mensaje que solo da los recuentos, sin ids ni nombres, y no cambia nada (`tests/integration/test_migrations.py::test_la_0004_no_se_aplica_si_hay_filas_que_la_incumplen`).
- **Política solo de `INSERT` `demo_space_from_parent`:** `WITH CHECK (kind = 'demo' AND parent_tenant_id = cuenta fijada)`. `tenant_isolation` no cambia: leer, actualizar y dar de alta una cuenta normal siguen exigiendo `id` igual a la cuenta fijada.
- **Trigger `tenants_check_hierarchy`** (`BEFORE INSERT OR UPDATE`, también para el propietario): al actualizar, `id`, `kind` y `parent_tenant_id` no cambian; al insertar un `demo`, la cuenta padre tiene que verse desde la transacción y ser `standard`. SQLSTATE `KZF14` (arquitectura §5.4).
- **`SECURITY INVOKER`, a propósito.** El trigger busca al padre con RLS aplicado: para la app, un padre ajeno y uno inexistente no se ven y dan el mismo error, así que no sirve de oráculo de existencia de otras cuentas. Como es `BEFORE`, falla antes que la clave foránea, que sí los distinguiría. Con `SECURITY DEFINER` vería todas las cuentas, y un espacio podría colgar de una cuenta ajena.
- **`kapataz_app` solo tiene `UPDATE (name)` en `tenants`**, no `UPDATE` de la tabla.

**Tres entradas, un núcleo** (S3-R-03). Las tres cargas comparten `demo_space_loader.load_demo_space`, que crea y llena el espacio de la cuenta que recibe, sea cual sea:

- **`LoadDemoSpace`**, la de la API (el botón «Cargar datos de ejemplo»): `execute(user: AuthenticatedUser, build)` toma la cuenta de `user.tenant_id` y nunca recibe un id.
- **Administración**, en `application/use_cases/admin/`: `LoadDemoSpaceForAccount` elige la cuenta por email (`tools/seed_demo.py --account`) y `LoadDemoSpaceForAccountId` por id (`--account-id`).

Dos contratos de import-linter impiden que la API elija la cuenta:

- `kapataz.api` no importa `admin/`;
- tampoco importa directamente `demo_space_loader` («La API carga el espacio de demostración solo de la cuenta de la sesión (S3-R-03)»). Lleva `allow_indirect_imports = true` a propósito, porque la API sí llega al núcleo a través de `LoadDemoSpace`.

Límite conocido: `AuthenticatedUser` es un dataclass que cualquiera puede construir con el `tenant_id` que quiera. El tipo no lo impide. Lo que protege es la convención de que la API solo lo obtiene de la dependencia `get_current_user`, que sale de la sesión (`api/dependencies.py`).

Desde S3-R-08 la vigila una prueba AST, `tests/security/test_api_aislamiento_estructural.py` (RN-10, A01). La prueba comprueba que:

- solo `AuthenticateSession` construye `AuthenticatedUser`, y nadie en `src/kapataz` lo copia cambiando `tenant_id`;
- nada en `api/` nombra el núcleo ni importa nombres privados o dinámicos de `kapataz`.

`load_demo_space.py` importa el núcleo con un alias privado y declara `__all__ = ["LoadDemoSpace"]`, porque import-linter no ve las reexportaciones. Cuando exista la ruta del botón, se añade `test_a01_idor_todas_las_rutas`.
