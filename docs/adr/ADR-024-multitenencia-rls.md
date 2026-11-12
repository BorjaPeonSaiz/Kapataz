# ADR-024 — Multitenencia con Row Level Security

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
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
- El espacio de demostración es un tipo de cuenta: `tenants.kind` vale `demo` y `parent_tenant_id` guarda la cuenta a la que pertenece. Su borrado lo hace una función de mantenimiento que solo actúa sobre ese tipo de cuenta.
- **Tablas globales sin RLS, en una lista cerrada.** Algunas tablas se leen antes de saber de qué cuenta se trata: al iniciar sesión, al validar la cookie o al recibir un webhook de Stripe. Esas tablas no llevan RLS: `users`, `sessions`, `subscriptions`, `payment_events` y las de plataforma (`platform_settings`, `platform_admins`, `platform_audit_events`). Solo las consulta un repositorio de cuentas acotado.
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
