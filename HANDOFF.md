# HANDOFF

Memoria de continuidad entre sesiones. Lo actualiza solo el hilo principal (plan maestro, §6.3). Si Engram y este archivo se contradicen, vale este archivo.

## Estado y objetivo actual

- **Bloques 0 y 1:** cerrados. PR #3 integrado el 12/11/2026 (`12e5edb`) y PR #4 el 17/11/2026 (`c4a95c0`). La prueba del Bloque 1 con un móvil real queda pendiente como excepción aprobada (ver «Pendiente»).
- **Bloque en curso:** 2 — Dominio y persistencia, en la rama `bloque-02-dominio` (plan maestro, §Bloque 2).
- **`main`:** protegida desde el 17/11/2026, con el check `ci` obligatorio, la rama al día, conversaciones resueltas y también para administradores; sin force push.
- **Demo de portafolio y sin despliegue hasta el Bloque 12** (Borja, 17/11/2026; plan maestro §1.5, ADR-014): todo se construye y se prueba en local. La 1.0.0 es la demo que supera la Parte II, y publicarla no abre el registro mientras quede algún pendiente legal (RN-13).
- **Decisiones de Borja del 18/11/2026:**
  - `billing_chain_heads` guarda solo el enlace al último registro (`last_record_id`, nulo con la cadena vacía), con la clave foránea compuesta `(tenant_id, last_record_id)`. Recogido en §4.5 del plan y en la arquitectura §5.2.
  - La cuenta no lleva el email como nombre: `tenants.name` admite nulos y se rellena con los datos del profesional.
  - La factura guarda una copia de nombre, NIF y domicilio del emisor y del destinatario (§4.5 y arquitectura §5.2).
  - La huella del `BillingRecord` sigue desde ya el algoritmo oficial de la AEAT (especificación v0.1.2; ADR-012 modificado).
  - ADR-009 recoge el cálculo con `Fraction` y un solo redondeo, y el tope de `Money` (21.474.836,47 €), comprobado al crear el borrador.
  - RN-F-06 exige el domicilio del emisor y del destinatario (art. 6 del RD 1619/2012), en el plan y en la especificación.
  - Las dudas fiscales del cálculo quedan provisionales y van a la lista del asesor (más abajo).
- **Hecho en el Bloque 2:**
  - F-05 y M-03 de las revisiones del Bloque 1: fábrica común `add_account` para el registro y la cortesía, migración `0002_nombre_de_cuenta` (vacía los nombres existentes) y prueba A09 con un error de base de datos forzado contra PostgreSQL.
  - El fixture `captured_logs` pasa a `tests/conftest.py`.
  - **Dominio puro** (`arquitecto-python`; commit de la fase 2):
    - objetos de valor, `TaxId` con dígito de control, clientes, catálogo, presupuestos con versiones, facturas, rectificativas, cobros y `BillingRecord` con la huella oficial (los tres ejemplos de la AEAT como pruebas);
    - cálculo de importes, IVA de la obra, regla del 40 %, fases y rectificativa por exceso, en `domain/billing`.
  - **Pruebas de propiedades** (`qa-testing`): `test_totales_propiedades.py` y `test_fases_propiedades.py`, con un perfil de hypothesis `ci` (200 ejemplos, se activa con `CI`) y otro `exhaustivo` para lanzarlo a mano.
  - **Persistencia** (`backend-fastapi`; commit de la fase 3):
    - migración `0003_facturacion` con 13 tablas, RLS en todas, FK compuestas `(tenant_id, …)`, céntimos `INTEGER` con un único conversor (`persistence/money.py`) y permisos mínimos;
    - triggers `KZF02` (factura emitida, sus líneas y correcciones inmutables) y `KZF07` (registros solo actualizables en las columnas de envío; la cabeza solo avanza al registro siguiente; `UNIQUE (tenant_id, previous_record_id) NULLS NOT DISTINCT` impide bifurcar la cadena);
    - repositorios, unidad de trabajo ampliada, `Professional` en `domain/settings` e `IssueInvoice` (factura → cabeza → contador, en una transacción) con `NullBillingRecordSubmission`;
    - datos de partida para pruebas en `tests/billing_support.py` y fixtures en `tests/integration/persistence/conftest.py`.
  - **Concurrencia, inmutabilidad y aislamiento** (`qa-testing`; commit de la fase 4):
    - 20 emisiones en procesos separados (`spawn` y barrera) con una y con tres cuentas, F y R a la vez, la misma factura desde 10 procesos y relojes desfasados para RN-F-04; 10 de 10 repeticiones con cada configuración de roles;
    - inmutabilidad columna a columna con los dos roles;
    - recorrido del catálogo: toda tabla fuera de la lista cerrada tiene RLS y la política `tenant_isolation`, y toda FK entre tablas de negocio es compuesta. Una tabla de negocio nueva también hay que añadirla a `_seed_every_table`.
  - **Cierre (fase 4):** `TRUNCATE` rechazado también en `series_counters`, `billing_chain_heads` y `payments` (Borja, 19/11/2026; migración 0003, aún sin integrar). §4.5, la arquitectura §5.2 y las rutas de ADR-012 recogen lo construido.
  - **Correcciones de las revisiones de cierre** (aprobadas por Borja el 19/11/2026; commit de la fase 5):
    - S2-01: las funciones de la migración 0003 fijan `search_path` y nombran sus tablas con esquema; TEMPORARY retirado a PUBLIC y a `kapataz_app` (la migración falla si no lo consigue);
    - S2-02: la base de datos ata la emisión al contador y a la cadena (solo se inserta en borrador; el contador sube de uno en uno con su factura emitida; el alta coincide con emisor, número y fecha; un solo alta por factura; las rectificadas y fases anteriores citadas están emitidas); SQLSTATE nuevos KZF00, KZF01, KZF03, KZF04 y KZF12;
    - S2-04/I-02/I-01: la factura que sale de un presupuesto copia al emitir el destinatario y la vivienda y se le aplica RN-F-13; reglas del destinatario solo en `works_vat`; CHECK `ck_invoices_works_recipient`;
    - M-10: TRUNCATE con código neutro KZF00; I-03 e I-06 documentados en ADR-009, ADR-012 y la arquitectura §7;
    - I-05: cada puerto de §4.3 llega con el bloque que lo usa; ADR-017 se cierra en el Bloque 4;
    - CI: cobertura de `domain/` ≥ 90 %, regla de Semgrep contra `float` en `domain/billing` (`.semgrep/`) y `mutacion.yml` manual.
  - Segunda revisión de `seguridad-ia`: sin bloqueantes.
  - 787 pruebas con PostgreSQL y cobertura de `domain/` del 100 %.

### Bloque 0 (histórico)

- **Objetivo:** que el repositorio contenga todo el conocimiento del proyecto antes de la primera línea de código.
- **Estado:** cerrado. Condiciones de Anthropic (ADR-029) aceptadas por Borja el 12/11/2026.
- **Hecho:**
  - `CLAUDE.md` y los 10 agentes de `.claude/agents/`, copiados del plan.
  - `docs/01-especificacion.md`, generado del plan: 141 identificadores y 33 escenarios.
  - `docs/02-arquitectura.md`, con §Diseño alineada con la marca de kodigolab.es.
  - `docs/03-modelo-amenazas.md` y `docs/04-evaluacion-ia.md`.
  - ADR-001 a ADR-033 con su índice en `docs/adr/README.md`.
  - `.engram/` añadido a `.gitignore`.
- **Decisiones aprobadas por Borja el 12/11/2026** (aplicadas al plan, la especificación, la arquitectura, el modelo de amenazas y los ADR):
  1. Se bloquea la cabeza de la cadena (`billing_chain_heads`) antes que el contador.
  2. RN-F-04 se comprueba con el contador ya bloqueado.
  3. Excepción de RN-03 para importes con IVA incluido: la cuota es la diferencia.
  4. Los esquemas Pydantic de las herramientas van en `application/agent`.
  5. Clases en inglés; las herramientas del agente, en español.
  6. Tablas nuevas: `tenants.kind`, `platform_admins`, `platform_audit_events` y `submission_authorizations`.
  7. Tablas globales sin RLS en una lista cerrada, y agregados del superadministrador con `SECURITY DEFINER`.
- **Arreglos menores aprobados y aplicados:**
  - gemelos `Fake` que faltaban;
  - marcador `owasp`;
  - ADR-030 se cierra en el Bloque 6;
  - RNF-01 incluye los datos del profesional;
  - `static/` y `docs/api/` en el árbol;
  - Semgrep y gitleaks en el stack;
  - `Payment` en el glosario.
- **Diseño:** paleta y tipografía de kodigolab.es (terracota, crema y marrón; Poppins e Inter), con el botón y los enlaces en `#B04E24` para cumplir AA. Los contrastes están en §Diseño.

## Siguiente acción

1. Con el visto bueno de Borja, subir `bloque-02-dominio` y abrir el PR único del Bloque 2 contra `main`; integrar con el CI en verde.
2. Después, lanzar `mutacion.yml` sobre la rama para tener la cifra de referencia (no bloquea el Bloque 2).
3. Bloque 3 del plan maestro.

## Pendiente

### Despliegue en el VPS (Bloque 12; respuestas del administrador del 12/11/2026, recogidas en ADR-014)

- Respondido:
  - El proxy es el nginx de KronoQR.
  - La red compartida es `kronoqr-app`, con la subred 172.18.0.0/16 de confianza.
  - Los secretos van en `/opt/kapataz/.env`.
  - `kapataz.kodigolab.es` es producción, y no habrá staging: solo local y producción (Borja, 12/11/2026).
  - Volúmenes `kapataz-db-data` y `kapataz-uploads`.
  - Despliegue manual por imagen etiquetada y vuelta atrás a la etiqueta anterior.
- Al desplegar la primera versión, el administrador añade al nginx el bloque de `kapataz.kodigolab.es`, apuntando a `kapataz:8000`, con:
  - redirección a HTTPS;
  - cabeceras `X-Forwarded-*`;
  - `proxy_buffering off` y tiempos de espera de 300 s para el SSE;
  - `client_max_body_size 50m`.
- Resuelto: uvicorn 0.54.0 admite CIDR en `--forwarded-allow-ips`, y hay una prueba que lo cubre.
- Requisitos del servidor (`docs/operacion/despliegue.md`):
  - Docker con Compose v2 2.24 o posterior, git, age y un usuario de despliegue en el grupo `docker`;
  - `.env` con permisos 600;
  - la clave pública de age en `.deploy/backup-recipients.txt`;
  - confirmar la subred real de `kronoqr-app`.
- Corregido en su propuesta:
  - la clave es `ANTHROPIC_API_KEY`, no `OPENAI_API_KEY`;
  - hasta la 1.0.0 las imágenes se etiquetan por commit, no `0.1.0` (ADR-032);
  - solo el servicio `kapataz` entra en `kronoqr-app`, y la base de datos queda en una red interna.

### Prueba del Bloque 1 con un móvil real (excepción aprobada)

- Iniciar sesión en `https://<IP>:8443` desde un móvil real y comprobar que el chat responde con `FakeLlm` (`sh deploy/local-up.sh --https <IP>`; guía en `docs/operacion/https-local.md`). Anotar móvil, navegador y resultado, y marcar la casilla de mkcert del Bloque 1 en el plan maestro.
- En el portátil funciona (`https://192.168.4.37:8443`); desde el móvil no abre. El cortafuegos activo es el de Bitdefender, que sustituye al de Windows, y la regla para `com.docker.backend.exe` con el puerto 8443 no bastó.
- Por revisar: tipo de red de la Ethernet en Bitdefender (Hogar/Oficina) y modo oculto; que el móvil esté en `192.168.4.0/22` y no en una red de invitados; el error exacto del móvil; probar con el cortafuegos desactivado un momento. El portátil también tiene la Wi-Fi conectada (`192.168.4.33`).

### Pendiente técnico del Bloque 1

- **`email_verifications`:** en la lista cerrada de tablas sin RLS (§4.5, ADR-024 y arquitectura §5.4), porque se lee antes de conocer la cuenta. **Confirmado por Borja el 17/11/2026.**
- **mypy:** revisa en estricto `src/kapataz` y `tools/`, pero no las pruebas (182 errores de anotaciones). Hay que tiparlas o darles una configuración propia antes de la Parte II.
- **Trazabilidad:**
  - **Pruebas sin `req`:** 53 en el backend y 2 en el frontend.
    - Son las 19 de `traceability.py`, ningún requisito trata de la trazabilidad, y 34 de infraestructura: adaptadores y dobles, SPA, health, OpenAPI, migraciones y cabeceras que no son HSTS. Cada una lleva un comentario «Sin req» con el motivo.
    - Hay que decidir antes de la Parte II cómo se trazan.
  - **Convención del frontend:** `req('ID')` y `owasp('A0X')` al final del título de la prueba, desde el 17/11/2026.
  - **Lo que `traceability.py` aún no hace:** listar las pruebas del frontend sin marcador. Hay que ampliarlo antes de la Parte II.
  - **Requisitos marcados como cubiertos que solo lo están en parte:**
    - RF-CO-01: las herramientas llegan en el Bloque 6;
    - RF-CF-04: solo se comprueba la regla del espacio de demostración;
    - RNF-10: los contrastes automáticos llegan en el Bloque 10.

    `--strict` no lo detecta.
  - las categorías OWASP cubiertas por etapas de CI (A03 y parte de A02 y A06) están pendientes en ADR-021.
- **Cuentas de cortesía:** se crean como cuenta normal; el paso al espacio de demostración (RN-13, RF-CF-04) llega con `tenants.kind` en uso.
- **Bloque 4:**
  - variable de configuración para la ruta de subidas (el volumen se monta en `/data/uploads`);
  - latido real del worker.
- **Bloque 6:** `LlmPort` aún no exige `SanitizedPrompt` (ADR-030).
- **Bloque 10:**
  - límite de intentos de login y bloqueo creciente (ADR-025);
  - service worker de la PWA (volver a añadir `vite-plugin-pwa` sin cachear `/api`);
  - copias fuera del servidor, archivado de WAL y copia de `kapataz-uploads`.
- **`tests/e2e_api/test_transporte.py`:** contra producción, tras el primer despliegue (Bloque 12).
- **Revisión de seguridad de cierre del Bloque 1** (`seguridad-ia`, 17/11/2026). Corregidos en este PR:
  - F-01: la URL de `kapataz_owner` ya no llega a la api ni al worker;
  - F-05, en parte: SQLAlchemy con `hide_parameters`;
  - F-06: `vue/no-v-html` es error y el lint falla con avisos.

  Pendientes:
  - **Bloque 4 o 10 (F-03):** el registro enumera cuentas por el tiempo de respuesta, porque el SMTP es síncrono y solo se envía si el email es nuevo; y con el registro cerrado, el 403 revela la lista de emails habilitados. O se aplica la solución, o Borja acepta el riesgo;
  - **Bloque 10, antes del Bloque 12:**
    - F-02: secuestro previo de cuenta; guardar el hash de la contraseña en `email_verifications` y aplicarlo al verificar;
    - F-04: Argon2 sin límite de concurrencia, que permite tumbar la api por memoria; añadir un semáforo y responder 429 o 503;
    - F-07: cookies con prefijo `__Host-` y CSRF ligado a la sesión;
    - cambiar o recuperar la contraseña debe revocar todas las sesiones;
  - **antes del Bloque 12 (F-08):** que `APP_ENV` sea obligatorio, sin el valor por defecto `local`, y que el health check compruebe que `/openapi.json` da 404 en producción;
  - **Bloque 12:** pedir al administrador que la base de datos de KronoQR no esté en `kronoqr-app`, y anotarlo en ADR-014.
  - **Restos de F-01, por decidir:**
    - `kapataz-admin` corre en `kapataz-tools` y recibe la URL del propietario sin usarla; se puede separar un servicio `kapataz-migrate`;
    - `deploy/deploy.sh` podría lanzar `deploy/check-compose-env.sh production .env` antes de migrar, pero haría falta jq en el servidor;
    - el `.env.local` del portátil conserva la línea antigua `DATABASE_MIGRATION_URL`. Llega vacía y es inocua, pero se puede borrar.
- **Revisión de código de cierre del Bloque 1** (`revisor-codigo`, 17/11/2026). Corregidos en este PR:
  - B-01 e I-01: marcadores de requisito;
  - M-01: comentarios de las plantillas `.env`;
  - M-02: este fichero;
  - M-07: `access_log off` en el bloque de nginx de producción.

  Pendientes:
  - M-04: los mensajes repiten constantes (`MIN_PASSWORD_LENGTH`, 4000); `InvalidChatMessageError` está en `application`, pero hereda de `DomainError`;
  - M-05: `FakeLlm` y `FakeEmail` acumulan mensajes y tokens en memoria en la app real; la captura debería existir solo en las pruebas;
  - M-06: el CI no comprueba que `schema.d.ts` esté al día, y `problem.ts` no cubre todos los tipos de error del backend;
  - M-08: añadir al glosario que `Account` y `Courtesy` se usan en código para la cuenta y la cuenta de cortesía.
- **HTTPS local (hallazgos de `plataforma-entrega`, 17/11/2026):**
  - en local, nginx ve siempre la puerta de enlace de Docker Desktop, así que la IP real del cliente solo se prueba en producción;
  - entrar por `https://localhost:8443` deja HSTS fijado para `localhost` y rompe `http://localhost:8000`, así que se entra por la IP o por `127.0.0.1`;
  - mezclar órdenes de Compose a mano con `local-up.sh` recrea `kapataz-db`, sin perder datos (la ruta del proyecto llega escrita de dos formas);
  - confiar en toda la subred de `kronoqr-app` permite que cualquier contenedor de KronoQR falsee `X-Forwarded-For` y `X-Forwarded-Proto`. Es el riesgo ya aceptado en ADR-014 y T-69; si se quiere cerrar, la alternativa es fijar la IP del nginx en el Bloque 12.
- **Texto del frontend:** `frontend/src/i18n/es-ES.ts` dice «El registro está cerrado hasta el lanzamiento». Sigue siendo válido, pero conviene revisarlo con RN-13 nueva.
- **npm:** 14 vulnerabilidades moderadas en herramientas de desarrollo (`minimatch` y `glob`), sin arreglo compatible. Ninguna alta, ninguna en producción.
- **Restos del build:** `backend/src/kapataz/static/` tiene restos del build del frontend. La carpeta está en `.gitignore`, pero conviene vaciarla; el comprobador de seguridad impidió a un agente borrarlos.

### Huecos de la persistencia del Bloque 2 (`backend-fastapi`, 18/11/2026)

- **Lectura de facturas emitidas** (resuelto el 19/11/2026: se leen con sus importes guardados, sin reglas de emisión; `IssuedAmountsMismatchError` si no cuadran). Queda:
  - los objetos de valor se siguen validando al leer (`TaxRate`, longitudes de líneas, partes, número y `SystemInfo`, dígito de control del NIF; `BillingRecord` se reconstruye con su constructor): endurecerlos rompería la lectura de lo emitido;
  - si cambia el cálculo de importes (ADR-009), las emitidas dejarán de cargarse; antes hará falta un ADR que haga de los importes guardados la fuente de verdad;
  - Bloque 8: un borrador que incumpla una regla endurecida no se puede abrir; leerlo e informar de qué incumple;
  - revisar si `quote_repository.py` tiene el mismo patrón con las versiones de presupuesto enviadas.
- **Bloque 8:**
  - conectar `IssueInvoice` a `bootstrap` con `SystemInfo` configurable (NIF de KodigoLab y número de instalación);
  - actualizar el estado del presupuesto al emitir;
  - traducir en la API los SQLSTATE de la migración 0003: `KZF00` (TRUNCATE), `KZF01` (numeración), `KZF02` (emitida inmutable), `KZF03` (rectificada no emitida), `KZF04` (fecha del contador que retrocede), `KZF07` (cadena) y `KZF12` (fase anterior no emitida);
  - una sola emisión por transacción: el trigger diferido exige `contador = número`; si un caso de uso emite dos facturas de la misma serie juntas (reparto 10 %/21 % de RN-F-13), habrá que pasar a `last_number >= number` (igual de seguro, porque el contador ya liga cada número a su factura); requiere aprobación;
  - decidir si `payments.invoice_id` solo admite facturas emitidas (¿se cobra un anticipo antes de emitir?);
  - corregir un cobro mal apuntado (hoy `payments` no admite UPDATE ni DELETE).
- **RF-FA-08:** la emisión aún no escribe en `audit_events` (tabla de otro bloque).
- **Espacio de demostración (RN-13):** los triggers impiden borrar sus facturas emitidas; la función de mantenimiento necesitará una excepción controlada.
- **Pruebas:** `tests/integration/test_rls.py::test_toda_tabla_sin_rls_esta_en_la_lista_cerrada` queda cubierta por la prueba nueva del catálogo; se puede retirar.
- **Zona horaria:** la fecha de expedición es la de hoy en Europe/Madrid. En Windows, `zoneinfo` depende del paquete `tzdata`, que solo llega como dependencia de desarrollo; la imagen trae el tzdata del sistema. Valorar declararlo como dependencia de la app.

### Hallazgos de las revisiones de cierre del Bloque 2 que no entran en su PR (19/11/2026)

Corregidos en el PR: S2-01, S2-02, S2-04/I-02/I-01, M-10, M-12 (dentro de S2-02), I-03, I-04, I-05, I-06.

- **Bloque 8 (`seguridad-ia`):**
  - S2-03: el `DETAIL` de los errores de PostgreSQL puede llevar nombres, NIF y domicilios a los logs; corregir antes de los endpoints que escriben clientes o facturas (falta confirmar si el `DETAIL` viaja en la excepción registrada);
  - S2-05: se puede construir a mano una `Invoice` «emitida» sin pasar por `issue`;
  - S2-09: el filtro de logs no reconoce los NIF que empiezan por K, L o M.
- **Bloque 12 (`seguridad-ia`):**
  - S2-06: `billing_records` no comprueba que sus columnas coinciden con el contenido de la huella; la base de datos tampoco comprueba la huella ni la fecha real de emisión, así que un rol de app comprometido aún puede montar por SQL una emisión coherente con datos falsos (ya sin huecos, duplicados, retrocesos ni bifurcaciones);
  - S2-10: la vuelta atrás de la migración 0003 borraría facturas; bloquearla con datos fiscales.
- **Segunda revisión de seguridad del cierre (19/11/2026), menores que no entran en el PR:**
  - RN-F-04 entre años: con SQL directo se puede abrir el contador de un año anterior con una fecha anterior a la última emitida de la serie, o emitir con fecha futura (el dominio sí lo impide); exigir en `series_counters_advance` el máximo de la serie en todos los años y un margen sobre `current_date`;
  - la base de datos no comprueba que el tipo de IVA encaje con el destinatario ni que la copia coincida con la versión del presupuesto (consultar al asesor antes de fijar la regla en la base de datos); `quote_versions` no tiene el CHECK de la vivienda;
  - Bloque 8: una rectificativa sin presupuesto toma el destinatario de quien la crea; atarla al de la factura rectificada;
  - la vuelta atrás de 0003 borra con DROP las tablas fiscales (ver S2-10); las pruebas necesitan una vía de escape;
  - `search_path` podría ser `pg_catalog, pg_temp`;
  - `.semgrep/` y `.github/` sin CODEOWNERS; la regla no detecta float implícito (división entre enteros);
  - confirmar que `source_paths` y `only_mutate` son claves válidas de mutmut 3.8.1.
- **Asesor fiscal:** S2-07 (que las rectificativas vayan obligatoriamente en su propia serie) y S2-08 (cambio de NIF del profesional con facturas emitidas).
- **Revisión de código (`revisor-codigo`), antes o durante el Bloque 8:**
  - I-07: las comprobaciones de RN-F-06 están en cuatro sitios (`missing_issue_data`, `issue`, `party.py`, `_parties` de `IssueInvoice`); la pantalla de confirmación y la emisión deben dar la misma lista;
  - M-01: `check_issue_date` se llama dos veces;
  - M-02: validaciones de texto copiadas (nombre de 120, texto sin bordes) en clientes, partes, profesional, líneas y presupuesto;
  - M-04: `works_vat` copia el redondeo de `Money.round` para el porcentaje de material;
  - M-05: lenguaje ubicuo (`BillingPhase` del glosario frente a `PhaseType`; `AdditionalWork` no existe como tipo); el glosario lo aprueba Borja;
  - M-06: marcadores `req` mal asignados (`test_repositorios.py`, `test_tax_id_and_customers.py`, `test_issue_invoice.py`);
  - M-07: higiene de pruebas (prueba de `NullBillingRecordSubmission` fuera de sitio; los campos obligatorios del XSD viven en el código que se prueba);
  - M-08: el doble en memoria se aparta del real (excepciones, `mark_issued`, orden de cobros, rectificadas en `add_draft`);
  - M-09: la arquitectura §7 y los comentarios de `issue_invoice.py` no describen el orden real de bloqueos ni `bootstrap`;
  - M-11: `_locked_head` es poco legible;
  - M-13: código sobrante y mensajes que repiten lo obvio.
- **Mutación (`plataforma-entrega`, 19/11/2026):** primera pasada de mutmut 3.8.1 sobre `domain/billing`: 76,3 % (2392 mutantes, 566 supervivientes; sobre todo `invoice`, `billing_record` y `quote`). El umbral del 80 % es de la Fase 3 del plan de verificación y de ADR-033 (Bloque 8), no del Bloque 2: `qa-testing` debe subirla antes. El job `mutacion.yml` es manual y falla por debajo del 80 %. mutmut entra con `uv run --with` sin hash: añadirlo al grupo `dev` y al lock (ADR-022).

### Por decidir en su bloque

- **Bloque 12, contraste con los esquemas de la AEAT** (interpretaciones provisionales del Bloque 2 en `billing_record.py`):
  - con inversión del sujeto pasivo (S2), `TipoImpositivo` y `CuotaRepercutida` van a `0.00`;
  - `RechazoPrevio` se trata como S/N (la AEAT admite también X) y `SinRegistroPrevio` siempre es N;
  - `FechaHoraHusoGenRegistro` se genera en UTC (`+00:00`).

- **Bloque 4 (ADR-026):** las tablas de la cola (`procrastinate`) no tienen RLS ni están en la lista cerrada de tablas globales. Hay que meterlas en la lista o limitar la prueba al esquema de la aplicación.
- **Bloque 6 (ADR-028):** límite de uso de IA para las cuentas de cortesía y de demostración.
- **Bloque 8:** vivienda alquilada en `recipient_type`, según el RDL 29/2026 (depende del asesor).
- **Bloque 12:**
  - envío a la AEAT fuera de la transacción de emisión;
  - que el espacio de demostración y las facturas anteriores a la 1.0.0 nunca lleguen a la AEAT de producción (P-07);
  - protección de las autorizaciones con copia del DNI (P-08).
- **En el bloque al que afecte cada una:**
  - 19 propuestas de seguridad abiertas (`docs/03-modelo-amenazas.md` §8; P-14 ya resuelta);
  - umbrales de evaluación sin fijar (`docs/04-evaluacion-ia.md`);
  - 13 preguntas de diseño abiertas (`docs/02-arquitectura.md`, §Diseño).

### Pendientes legales (demo)

Están listados en el plan maestro, §1.5. No bloquean ningún bloque ni la 1.0.0. Mientras quede alguno abierto, el registro sigue cerrado, ninguna factura es real y solo se usan datos sintéticos (RN-13):

- validación fiscal de un asesor (Bloques 8 y 12);
- declaración responsable firmada (Bloque 12);
- contrato con el proveedor de envío y autorización real de cada cliente (Bloque 12);
- textos legales revisados por un abogado (Bloque 10);
- retención cero, transferencia y subencargados de Anthropic (Bloque 6);
- pago real con Stripe (Bloque 10).

### Respuestas de asesores

Son el detalle de los pendientes legales. No bloquean los bloques de la demo.

- **Asesor fiscal:** reglas de IVA de la facturación por fases (ADR-033, Bloque 8), aplazamiento de VERI*FACTU para el productor, importe total del registro y validación final (Bloque 12).
  - **Interpretaciones provisionales del Bloque 2** (aisladas en `domain/billing`; aprobadas por Borja el 18/11/2026 a la espera del asesor):
    - base del 40 % de material: solo las líneas de la obra, sin lo que va fuera de ella ni las restas de fases (`works_vat.material_share`);
    - si las fases que hay que rectificar van a tipos de IVA distintos, una rectificativa por tipo (`phases.plan_final_phase`); el plan habla de «una rectificativa»;
    - sin decidir: anticipo y certificaciones al 21 % y final al 10 %; hoy el dominio no lo resuelve, decide quien llama;
    - anticipo cobrado con retención de IRPF: el importe cobrado se trata como el total con IVA (`calculation.totals_from_gross`).
  - **Fecha de expedición en Europe/Madrid** (`issue_invoice.FISCAL_TIMEZONE`, ADR-012): en Canarias solo cambiaría la fecha entre las 23:00 y las 00:00 de allí; confirmar con el asesor.
- **Abogado:** condiciones de uso, contrato de encargo, política de privacidad, aviso de IA y plazos de conservación (antes de producción, Bloque 10). Comprobar también la lista oficial del Marco de Privacidad.
- **Proveedores de envío VERI*FACTU:** elección del proveedor y autorización de cada cliente (Bloque 12).
- **Anthropic:** retención cero, canal de aviso de subencargados e información para la evaluación de la transferencia (antes de usar datos reales, ADR-029). Revisar a mano la lista de subencargados, que no se pudo leer automáticamente.
- Crear la cuenta de la API de Claude con el email de la empresa: no se puede cambiar después.

## Trampas del entorno

- **Python en Windows:** no hay `python` en el PATH (el de `WindowsApps` es el acceso directo a la Microsoft Store). En `backend/`, todo va con `uv run …`; fuera, con `uv run --no-project --python 3.12 python …`.
- **Docker Desktop:** hay que arrancarlo a mano antes de las pruebas de integración o de `deploy/local-up.sh`.
- **Red `kronoqr-app` en el portátil:** existe y es la del entorno de desarrollo de KronoQR (`kronoqr-nginx`, `kronoqr-postgres`). Kapataz se une a ella en local igual que en el servidor. No hay que borrarla nunca.
- **PostgreSQL de pruebas:** las de integración necesitan `TEST_DATABASE_URL` (y `TEST_DATABASE_MIGRATION_URL` si se separan los roles). Sin ella, se saltan con su motivo.
- **Finales de línea:** `.gitattributes` fuerza LF en `*.sh`, `Dockerfile` y `*.yml`. Con CRLF fallan el init de PostgreSQL y los scripts de despliegue.
- **ShellCheck en PowerShell:** no expande `deploy/*.sh`; hay que lanzarlo desde Bash.
- `docs/consultas/` está en `.gitignore`: las consultas a profesionales son privadas y solo existen en local.
- `docs/01-especificacion.md` se genera desde §1 y §3 del plan: si cambia un RF, RN o RNF, se cambia en el plan y se regenera, o se editan los dos a la vez.
- Los diagramas Mermaid de `docs/02` y `docs/03` no se han renderizado; solo se ha revisado la sintaxis a mano.
- markdownlint avisa de MD060 en todas las tablas (estilo compacto `|---|`, el mismo del plan). No es un error.
