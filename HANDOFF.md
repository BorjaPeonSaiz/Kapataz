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
- **Hecho en el Bloque 2:**
  - F-05 y M-03 de las revisiones del Bloque 1: fábrica común `add_account` para el registro y la cortesía, migración `0002_nombre_de_cuenta` (vacía los nombres existentes) y prueba A09 con un error de base de datos forzado contra PostgreSQL.
  - El fixture `captured_logs` pasa a `tests/conftest.py`.

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

1. **Dominio puro** (`arquitecto-python`): objetos de valor (`Money`, `TaxRate`, `Quantity`, `TaxId`, `Series`, `DocumentNumber`), entidades y cálculo de importes, con pruebas de propiedades (hypothesis, `qa-testing`). Sin base de datos; se revisa antes de seguir.
2. **Persistencia** (`backend-fastapi`): puertos con sus `FakeX`, migraciones del modelo de §4.5 con RLS, triggers de inmutabilidad y contadores, repositorios, unidad de trabajo e `IssueInvoice`.
3. **Pruebas de concurrencia, inmutabilidad y aislamiento** (`qa-testing`), cierre de ADR-017 y revisiones de seguridad y de código.
4. Un solo PR del bloque, con commits separados por fase.

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

### Por decidir en su bloque

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
