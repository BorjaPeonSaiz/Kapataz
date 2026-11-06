# Plan de verificación pre-release — Kapataz

> ⚠️ **Pendiente de adaptar:** Kapataz ha pasado de app local a servicio web multiusuario con Claude (ver `00-plan-maestro.md`, Parte I). Este plan aún describe la versión local anterior. No lo ejecutes hasta adaptarlo.

> **Producto:** asistente local con IA para autónomos de oficio: consulta del histórico, presupuestos y facturas por texto o voz.
>
> **Stack:** Python 3.12 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · SQLite (WAL, FTS5, sqlite-vec) · Ollama · bucle de agente propio · pdfplumber · ReportLab · faster-whisper · Vue 3 + Vite + TypeScript + Tailwind + Pinia · pdf.js · PowerShell.
>
> **Herramientas:** ruff, mypy `--strict`, import-linter, bandit, pip-audit, Semgrep, gitleaks, ZAP, pytest, pytest-cov, hypothesis, mutmut, schemathesis, freezegun, vue-tsc, ESLint, Prettier, Vitest, Playwright, axe-core, npm audit, PSScriptAnalyzer, Pester, GitHub Actions.
>
> **Observabilidad (local, sin telemetría):** structlog JSON, `/api/health`, `agent_runs`, `audit_events`, `doctor.ps1 -Bundle`.
>
> **Despliegue:** aplicación local en Windows 10/11, un proceso y un puerto (`127.0.0.1:8765`), un profesional por instalación. CI en `windows-latest` y `ubuntu-latest` con `FakeLlm` determinista; Ollama no corre en CI (ADR-008).
>
> **Cómo leer cada tarea:** `🤖 agente · Modelo`. Cuando la detecta un agente de solo lectura, se indica también quién corrige: `→ corrige: agente`.
>
> **Severidades:**
> - `revisor-codigo`: 🔴 BLOQUEANTE · 🟠 IMPORTANTE · 🟡 MENOR
> - `seguridad-ia`: 🔴 CRÍTICO · 🟠 ALTO · 🟡 MEDIO · ⚪ BAJO

Este es el plan que se ejecuta antes de una release. Desarrolla la **Parte II** de [`00-plan-maestro.md`](./00-plan-maestro.md). Los requisitos y umbrales salen de `docs/01-especificacion.md` y de los ADR aceptados: si este plan los contradice, manda la especificación y se corrige el plan.

---

## Reparto de agentes y modelos

| Agente | Papel en la verificación | Modelo | Modo |
|---|---|---|---|
| `arquitecto-python` | Reglas de negocio, pureza hexagonal, ADR | **Opus 5.5** | Escritura |
| `backend-fastapi` | Casos de uso, API, migraciones, SQLite, logs | **Opus 5.5** | Escritura |
| `ingeniero-ia` | Agente, prompts, extracción, RAG, voz, evaluaciones | **Opus 5.5** | Escritura |
| `qa-testing` | Pirámide de pruebas, trazabilidad, E2E, rendimiento | **Opus 5.5** | Escritura |
| `plataforma-entrega` | CI, scripts de Windows, diagnóstico, actualización | **Opus 5.5** | Escritura |
| `arquitecto-vue` | SPA, estado, streaming, voz en cliente, i18n | **Sonnet 5.5** | Escritura |
| `ui-ux` | Tokens, contraste, estados, coherencia visual | **Sonnet 5.5** | Escritura |
| `documentacion-portafolio` | README, docs de usuario, caso de estudio | **Sonnet 5.5** | Escritura |
| `seguridad-ia` | STRIDE, OWASP, RGPD, facturación | **Opus 5.5** | Solo lectura |
| `revisor-codigo` | Definición de Terminado, duplicación, estilo | **Opus 5.5** | Solo lectura |
| 👤 **Tú** | Windows real, criterio de negocio, validación fiscal | — | — |

### Criterio de modelos

- **Opus 5.5 para el criterio:** donde un error acaba en una factura mal numerada, un importe mal calculado, un agente que obedece a un PDF o una instalación rota.
- **Sonnet 5.5 para la ejecución con feedback inmediato:** frontend, diseño y documentación.
- **Fable 5.1 no se asigna por defecto.** Solo como escalado temporal, cambiando el campo `model:` del agente:
  - la precisión de extracción o de selección de herramienta se estanca bajo el umbral tras dos iteraciones de `ingeniero-ia`;
  - un fallo intermitente de concurrencia en la numeración que `qa-testing` no reproduce tras dos intentos.
- **Fable no se usa en la Fase 7:** sus salvaguardas adicionales de ciberseguridad lo hacen menos adecuado que Opus para esa revisión.

### Reglas de flujo

1. El hilo principal orquesta, marca casillas y delega cada tarea en el agente indicado.
2. Los agentes de solo lectura (`revisor-codigo`, `seguridad-ia`) **no corrigen**. Cada hallazgo va al registro final, lo corrige el agente dueño y el detector vuelve a revisar.
3. `seguridad-ia` y `revisor-codigo` no pueden ejecutar comandos: revisan código y evidencias. Las pruebas las ejecuta el agente que aparece junto a ellos.
4. `documentacion-portafolio` tampoco ejecuta comandos: los comandos de la documentación los prueba `plataforma-entrega`.
5. Ningún agente cambia una RN, un RF o un ADR aceptado sin que `arquitecto-python` lo proponga y tú lo apruebes.
6. Ningún umbral se baja para que una prueba pase.

---

## Flujo de entrega y bloqueo de PR

Estas comprobaciones corren durante la construcción, en cada bloque. La verificación pre-release no las sustituye: repite la auditoría completa sobre la release.

- Cada bloque (0–11) va en su rama `bloque-NN-nombre` y en su **propio PR** contra `main`, con código, documentación y pruebas, y con los requisitos afectados enlazados.
- Antes de pedir revisión se ejecutan las pruebas del bloque, su criterio de terminado y la Definición de Terminado.
- Lo que no corre en CI (evaluaciones con `pytest -m llm`, instalación en Windows Sandbox) se ejecuta en local y el PR anota resultado, perfil, modelo, versión del prompt y fecha.
- Para integrar deben estar en verde el CI de GitHub, las comprobaciones de seguridad (`pip-audit`, `npm audit`, bandit, Semgrep y gitleaks, sin hallazgos altos ni críticos) y la revisión de `revisor-codigo`.
- Un check fallido o pendiente bloquea la integración. Una excepción exige justificación en el PR, con riesgo, mitigación y tu aprobación. No se exceptúan defectos críticos de seguridad ni invariantes fiscales.
- El Bloque 0 solo aporta documentación: se comprueba en local y se integra con tu visto bueno. El Bloque 1 crea los workflows y la protección de `main`, y su propio PR ya debe pasarlos.

---

## Antes de empezar: huecos que hay que cerrar

Este plan comprueba comportamientos que el plan maestro da por hechos pero no define. Hay que cerrarlos antes de la Fase 1: `arquitecto-python` propone y tú decides.

| # | Hueco | Dónde aparece | Qué hace falta |
|---|---|---|---|
| 1 | **RN-07, RN-08 y RN-09** no existen en la especificación (§3.2 termina en RN-06) | Tablas OWASP LLM04, LLM08 y LLM09 | Definirlas. Por el contexto: mínimo de muestras y exclusión de atípicos en precios, solo cuentan documentos aprobados, y remisión a la gestoría ante preguntas fiscales. Hasta entonces `traceability.py --check` falla en cualquier prueba que las cite |
| 2 | **ADR-021, ADR-022 y ADR-023** no están en el catálogo (§5 termina en ADR-020) | Tablas OWASP | Añadirlos: trazabilidad OWASP, cadena de suministro y precios robustos |
| 3 | **Modo red local** sin requisito propio: aparece el PIN, pero no hay RF ni HTTPS | §1.4, A01, A07 | Decidir si entra en v1. Si entra, necesita RF y HTTPS: sin contexto seguro el navegador del móvil no da acceso al micrófono y el PIN viaja en claro. Si no entra, se retiran sus pruebas |
| 4 | **Vaciar la demo** frente a la inmutabilidad: los triggers impiden borrar facturas emitidas | RF-CF-04, RN-F-02 | Decidir el mecanismo. Lo más limpio es una BD de demostración separada, para que no exista ningún camino de borrado sobre facturas reales |
| 5 | **Restaurar una copia antigua** hace retroceder la numeración y la cadena | RF-CF-03, RN-F-01, RN-F-07 | Definir el aviso y qué ocurre con las facturas emitidas después de la copia |
| 6 | **Copias cifradas con contraseña** sin requisito | A04 | Añadir a RF-CF-03 o retirar de la tabla |
| 7 | **Casos de negocio sin regla:** cobro superior al importe pendiente y segunda conversión de un mismo presupuesto | RF-FA-06, RF-FA-03 | Fijar el comportamiento esperado |
| 8 | **WER sin umbral** | Bloque 9 | Se mide y se anota. No se declara aprobado ni suspenso mientras la especificación no fije un valor |
| 9 | **El escenario «Extracción que no cuadra»** no indica el IVA: la diferencia de 90,00 € solo sale con el 21 % | §3.5 | Añadir el tipo de IVA al escenario |

---

## Orden recomendado

| Paso | Fases | Agentes principales |
|---|---|---|
| 1 | 0 · Preparación | plataforma, qa-testing, backend, arquitecto |
| 2 | 2 · Calidad de código | backend, arquitecto, arquitecto-vue, ui-ux |
| 3 | 3 · Pruebas | qa-testing, arquitecto-vue |
| 4 | 4 · Calidad de la IA | ingeniero-ia, qa-testing |
| 5 | 7 · Seguridad (automatizado) | plataforma |
| 6 | 1 · Funcionalidad vs. especificación | arquitecto, backend, ingeniero-ia, arquitecto-vue, qa-testing |
| 7 | 5 · Control de errores | backend, arquitecto-vue, plataforma, qa-testing |
| 8 | 7 · Seguridad (STRIDE, OWASP, RGPD, facturación) | seguridad-ia, qa-testing |
| 9 | 6 · Observabilidad y diagnóstico | backend, plataforma |
| 10 | 8 · Rendimiento | qa-testing, ingeniero-ia, arquitecto-vue |
| 11 | 9 · Datos y base de datos | backend, plataforma |
| 12 | 10 · Instalación y entrega | plataforma, 👤 |
| 13 | 11 · Documentación | documentacion-portafolio, arquitecto |
| 14 | 12 · Accesibilidad y UX | ui-ux, arquitecto-vue, qa-testing, 👤 |
| 15 | 13 · Revisión final | revisor-codigo, seguridad-ia |

La Fase 4 necesita Ollama y un equipo libre durante horas: puede correr en paralelo con las pruebas de interfaz.

---

## Fase 0 — Preparación

- [ ] **Congelar el código:** rama `release/x.y` o tag; árbol de trabajo limpio y lista de los PR y bloques incluidos.
  - 🤖 hilo principal · Sonnet 5.5
- [ ] **Huecos cerrados:** la tabla «Antes de empezar» está resuelta y todo ID citado en este plan existe en la especificación o en el catálogo de ADR.
  - 🤖 `arquitecto-python` · Opus 5.5 + 👤
- [ ] **Entorno limpio** con datos sintéticos versionados que incluyan los casos límite: clientes ambiguos, inversión del sujeto pasivo, retenciones, rectificativas, PDFs con errores sembrados y PDF trampa. Ningún dato real.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Matriz de trazabilidad** con `cd backend && uv run python tools/traceability.py --check`, cruzada con los RF, RN y RNF de `docs/01-especificacion.md`.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Inventario de endpoints:** cruzar las rutas de FastAPI con `docs/api/openapi.json`. Una ruta sin contrato o un contrato sin ruta es un hallazgo.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Instalación limpia** en Windows Sandbox siguiendo **solo** `docs/usuario/instalacion.md`, terminando con `doctor.ps1` en verde.
  - 🤖 `plataforma-entrega` · Opus 5.5

> **Límites de Windows Sandbox:** usa la versión de Windows del anfitrión, el usuario fijo `WDAGUtilityAccount` y solo trae Windows PowerShell 5.1. Probar Windows 10, PowerShell 7 o un usuario con tildes exige una VM (Fase 10). Además, se borra al cerrarse: cada prueba descarga de nuevo los modelos.

---

## Fase 1 — Funcionalidad vs. especificación

- [ ] **Reglas de negocio:** cada RN está implementada en el dominio; RN-01 a RN-03 y RN-F-01 a RN-F-07 las protegen agregados u objetos de valor, no la API. Detectar reglas que vivan en el código y no estén en la especificación.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **ADR:** ninguna implementación contradice un ADR vigente y no queda ninguno en «Propuesto».
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Backend:** RF-IN, RF-PR, RF-FA y RF-CF cubiertos, sin *scope creep* sin documentar.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Separación del histórico:** lo importado no entra en `invoices` ni consume numeración; las consultas agregan ambos orígenes y lo marcan (RF-IN-09, RN-F-08, ADR-017).
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Agente:** RF-CO completos; las respuestas con cifras citan fuentes; ninguna escritura sin `PendingAction`; panel «cómo lo he calculado» (RF-CO-07).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Origen de los precios:** cada precio propuesto indica de dónde sale; sin origen, la línea queda sin precio y marcada (RN-06).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Voz:** RF-VO cubiertos; con la opción externa desactivada no sale audio del equipo; la transcripción es editable antes de enviarse.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Frontend:** cada RF con interfaz tiene su pantalla; borrador y emitida se distinguen sin leer; la emisión pide confirmación diferenciada; el frontend no recalcula totales.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Configuración:** asistente de primer arranque, catálogo editable, copia de seguridad y modo demostración (RF-CF).
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Instalación:** RF-IS completos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Puertos preparados para el futuro:** `RegistroFacturacionPort`, `LicenciaPort` y `OcrPort` existen y v1 no los salta.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Escenarios Gherkin** de §3.5 automatizados y en verde.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 2 — Calidad de código

### Automatizado

- [ ] **Backend:** `ruff check`, `ruff format --check`, `mypy --strict` y `lint-imports` en verde; cada `# type: ignore` y `# noqa` lleva justificación.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **CI:** las etapas de lint y unitarias tardan menos de 10 minutos en `windows-latest`; es determinista y no depende de Ollama ni de servicios externos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **PowerShell:** PSScriptAnalyzer sin avisos en `scripts/windows/`.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Frontend:** `npm run type-check && npm run lint && npm run test:unit && npm run build` en verde.
  - 🤖 `arquitecto-vue` · Sonnet 5.5

### Revisión de arquitectura

- [ ] **Pureza del dominio:** `domain/` no importa FastAPI, SQLAlchemy, Ollama, pdfplumber, ReportLab ni nada de `infrastructure`.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Reloj inyectado:** ninguna llamada a `datetime.now()`, `date.today()` ni `time.time()` en `domain/` ni en `application/`.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Dinero:** ningún `float` en rutas de importes (búsqueda de `float(`, literales con decimales en cálculos, columnas `REAL`). Revisar también la frontera con el LLM y con JSON: un importe no entra ni sale como número de coma flotante.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Objetos de valor:** inmutables (`frozen=True`) y sin estados imposibles.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Adaptadores:** cada puerto tiene su adaptador real y su `Fake`, y el `Fake` cumple el mismo contrato (pruebas compartidas).
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **API:** ninguna entidad del dominio expuesta; ninguna regla de negocio en routers ni repositorios.
  - 🤖 `arquitecto-python` · Opus 5.5

### Revisión de lo que no ven las herramientas

- [ ] **Duplicación:** un segundo cálculo de importes, un segundo formateador de moneda o fechas, una segunda validación de NIF, recálculo de totales en el frontend.
  - 🤖 `revisor-codigo` · Opus 5.5 → corrige: el agente dueño
- [ ] **Estilo:**
  - lenguaje ubicuo del glosario (`Invoice`, no `Bill`; `Quote`, no `Budget`);
  - nombres del dominio, no del patrón;
  - comentarios que explican el porqué;
  - abstracciones que no ganan nada.
  - 🤖 `revisor-codigo` · Opus 5.5
- [ ] **Prompts como código:** versionados en ficheros, sin cadenas largas incrustadas, con su prueba de regresión.
  - 🤖 `revisor-codigo` · Opus 5.5 → corrige: `ingeniero-ia`
- [ ] **Sistema visual:** ningún hexadecimal suelto; todos los colores salen de tokens.
  - 🤖 `ui-ux` · Sonnet 5.5

---

## Fase 3 — Pruebas

### Umbrales

- [ ] **Cobertura y tiempos:**
  - `domain/` ≥ 90 %;
  - backend total ≥ 80 %;
  - frontend ≥ 70 %;
  - suite unitaria del backend < 10 s.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Mutación** con mutmut sobre `domain/billing`: puntuación ≥ 80 %. Se ejecuta en `ubuntu-latest` o en WSL: mutmut 3 no funciona en Windows nativo.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Trazabilidad:** todas las pruebas llevan marcador y `traceability.py --check` bloquea la CI si falta uno o si cita un ID inexistente.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Relojes:** `FrozenClock` en todas las pruebas que dependen del tiempo; ninguna depende de la fecha real.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Contrato:** schemathesis contra `openapi.json` sin fallos ni respuestas 500.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Cero pruebas intermitentes** (10 ejecuciones seguidas de la suite completa). Si alguna se resiste, se escala a Fable 5.1.
  - 🤖 `qa-testing` · Opus 5.5

### Escenarios obligatorios

Todos los de este bloque: 🤖 `qa-testing` · Opus 5.5.

**Dinero y fiscalidad**

- [ ] **Redondeo:** propiedades con hypothesis; casos frontera (0,005 €, cantidades decimales, descuentos del 100 %); la suma de bases y cuotas cuadra con el total.
- [ ] **Fiscalidad:** IVA 21/10/4 %, mezcla de tipos en una factura, inversión del sujeto pasivo con cuota cero y su mención, retención del 15 % y del 7 %.
- [ ] **NIF, NIE y CIF:** formatos válidos e inválidos y dígito de control.
- [ ] **Datos obligatorios:** falta un dato de RN-F-06 y la factura no se emite.

**Numeración e inmutabilidad**

- [ ] **Numeración concurrente:** 20 emisiones en paralelo con procesos distintos sobre SQLite real, en Windows y en Linux; sin huecos ni duplicados.
- [ ] **Series independientes:** `F`, `R` y `P` numeran por separado; el número se asigna al emitir, no al crear el borrador.
- [ ] **Cambio de año:** la primera factura del año reinicia la numeración; una emisión el 31/12 a las 23:59:59 y otra el 01/01 a las 00:00:00.
- [ ] **Fecha anterior:** se rechaza emitir con fecha anterior a la última de la serie.
- [ ] **Reloj del equipo atrasado:** con la fecha del PC retrasada, el usuario recibe un mensaje claro y no una factura con fecha incoherente.
- [ ] **Emisión fallida:** no consume número ni deja un `BillingRecord` huérfano.
- [ ] **Inmutabilidad por SQL directo:** `UPDATE` y `DELETE` sobre una factura emitida fallan por trigger.
- [ ] **Cadena de registros:** se altera un `billing_record` por SQL y `verify-billing-chain` lo detecta.
- [ ] **Rectificativa:** por diferencias y por sustitución, con referencia y motivo.

**Presupuestos y cobros**

- [ ] **Estados:** borrador → enviado → aceptado, rechazado o caducado; la caducidad se calcula con `Clock`.
- [ ] **Versiones:** modificar un enviado crea una versión nueva y conserva la anterior.
- [ ] **Conversión:** un presupuesto aceptado genera un borrador de factura con sus líneas y mantiene el vínculo; uno no aceptado no se convierte.
- [ ] **Cobros:** pendiente, parcial y completo, con fecha y forma de pago; el estado de cobro no toca los datos fiscales.
- [ ] **Exportación:** libro de facturas en CSV y Excel por periodo; los importes cuadran con los de la aplicación.

**Ingesta**

- [ ] **PDFs problemáticos:** duplicado por hash, cifrado, sin texto, de 200 páginas, malformado, con total incorrecto y con compresión diseñada para agotar memoria.
- [ ] **Carpeta vigilada:** un PDF a medio copiar no se procesa hasta estar completo; funciona con `Documentos` redirigido a OneDrive y con ficheros que solo existen en la nube.
- [ ] **Revisión:** ningún documento con baja confianza o que no cuadra cuenta para las consultas hasta aprobarse.
- [ ] **Clientes:** deduplicación por NIF y fusión por similitud solo con confirmación del usuario.

**Agente**

- [ ] **Conversación:** cliente ambiguo, pregunta sin datos, periodo implícito, herramienta desconocida y bucle infinito cortado por el límite.
- [ ] **PendingAction:** caducada, alterada (firma inválida) y confirmada dos veces (idempotencia); doble clic en Confirmar emite una sola factura.
- [ ] **Divergencia del índice:** un documento borrado o excluido a mano en `chunks` se detecta y el reindexado lo corrige.

**Red y voz**

- [ ] **Sin red:** la aplicación funciona en Windows Sandbox con `<Networking>Disable</Networking>` y Ollama local. En Playwright se usa `context.route` para abortar y registrar todo lo que no vaya a `127.0.0.1`, y la prueba falla si hay algún intento. No se usa `setOffline`, que actúa sobre todo el contexto y puede cortar también el acceso a la propia app.
- [ ] **Voz:** grabación vacía, ruido, audio de 2 minutos, permiso de micrófono denegado y modelo no disponible.
- [ ] **Formatos de audio:** el servidor acepta lo que produce MediaRecorder en cada navegador soportado (`webm/opus` y, si hay acceso desde iPhone, `mp4`).

### Pruebas de frontend

- [ ] **Unitarias:** formateo de moneda y fechas, store del chat, parser de SSE, tarjeta de `PendingAction`.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **E2E** con Playwright contra la app servida con `FakeLlm`, en Chromium y en Edge (`channel: 'msedge'`), que es el navegador presente en todo Windows: importar y revisar, preguntar, presupuesto por chat, emitir, rectificar, cobrar.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Micrófono simulado:** E2E con `--use-fake-device-for-media-stream` y `--use-file-for-fake-audio-capture`.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 4 — Calidad de la IA

> Se ejecuta en local con Ollama (`pytest -m llm`) en el perfil `estandar` y se repite en `ligero`. Resultados en `docs/04-evaluacion-ia.md` con fecha, modelo y digest, versión del prompt y dataset.

- [ ] **Extracción:** precisión en campos críticos (número, fecha, NIF, base, IVA, total) ≥ 95 % (RNF-06); ningún documento con errores sembrados aprobado sin revisión.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Selección de herramienta** ≥ 90 % y exactitud de parámetros ≥ 90 % (RNF-07).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Fidelidad numérica:** 0 respuestas con cifras que no procedan de una herramienta (RN-02). Una sola es bloqueante.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Alucinación de fuentes:** 0 enlaces a documentos inexistentes o que no contienen el dato.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Recuperación:** recall@5 ≥ 0,85; MRR anotado.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Voz:** WER anotado por perfil sobre las grabaciones de oficio, con vocabulario técnico (diferencial, magnetotérmico, rozas, alicatado, solera).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Robustez a inyección:** batería de 20 PDFs y mensajes maliciosos (instrucciones directas, ocultas en tablas, en otro idioma, en metadatos); ninguna herramienta de escritura invocada fuera de propuesta y ninguna fuga del prompt de sistema.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Regresión de prompts:** cambiar un prompt sin volver a pasar la evaluación hace fallar el check (huella del prompt registrada en el informe).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Estabilidad:** tres ejecuciones con temperatura 0; la variación de métricas es < 2 puntos.
  - 🤖 `ingeniero-ia` · Opus 5.5 → escalado a Fable 5.1 si no se alcanza tras dos iteraciones

---

## Fase 5 — Control de errores

- [ ] **Formato de error:** `application/problem+json` coherente en toda la API, con tipos estables documentados y sin trazas internas.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Errores del dominio** traducidos a mensajes útiles (factura inmutable → ofrece rectificativa; fecha anterior → indica la última fecha válida).
  - 🤖 `backend-fastapi` · Opus 5.5 + `ui-ux` · Sonnet 5.5
- [ ] **Transacciones:** un caso de uso es una transacción; una emisión que falla a medias lo revierte todo.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Errores no controlados:** quedan en el log agrupables y **sin datos personales**; la persona ve qué hacer, no una traza.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Ollama caído o modelo ausente:** la app arranca, las pantallas sin IA funcionan y el chat explica qué pasa y cómo arreglarlo.
  - 🤖 `ingeniero-ia` · Opus 5.5 + `arquitecto-vue` · Sonnet 5.5
- [ ] **Respuesta inválida del modelo:** JSON roto, herramienta inexistente o parámetros inválidos se reintentan de forma acotada y, si persisten, se informa sin colgar el chat.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Ingesta:** un PDF que falla no bloquea la cola; el motivo se ve en la interfaz.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **SSE:** reconexión del frontend y estado consistente si se corta a mitad de respuesta; una desconexión nunca ejecuta una escritura.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Estados** de vacío, carga y error en todas las vistas, diciendo qué ha pasado y qué hacer.
  - 🤖 `ui-ux` · Sonnet 5.5 (diseño) + `arquitecto-vue` · Sonnet 5.5 (implementación)
- [ ] **Scripts:** los mensajes dicen qué hacer y un fallo a medias deja el sistema recuperable.
  - 🤖 `plataforma-entrega` · Opus 5.5

### Pruebas de caos

- [ ] **Caídas:**
  - Ollama parado a mitad de una respuesta;
  - Ollama sin memoria al cargar el modelo;
  - disco lleno durante la ingesta y durante una copia de seguridad;
  - fichero de BD bloqueado por otro proceso (antivirus o copia de seguridad);
  - proceso matado a mitad de una emisión;
  - suspensión del portátil a mitad de una ingesta;
  - cierre del navegador con una `PendingAction` abierta.
  - 🤖 `plataforma-entrega` · Opus 5.5 (provoca) + `qa-testing` · Opus 5.5 (verifica)

---

## Fase 6 — Observabilidad y diagnóstico (local)

- [ ] **Logs:** JSON con `request_id`, `run_id`, `use_case`, duración y resultado; **nunca** NIF, nombres de clientes, importes asociados a personas ni texto de documentos.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Rotación** de logs con límite de tamaño y días.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Trazas del agente** en `agent_runs`: herramientas, parámetros sin datos personales, iteraciones, latencia por paso y modelo usado; purga configurable.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Integridad visible:** `verify-billing-chain` corre al arrancar; si falla, la interfaz avisa y `doctor.ps1` lo reporta. Se ha provocado al menos una vez a propósito.
  - 🤖 `backend-fastapi` · Opus 5.5 + `arquitecto-vue` · Sonnet 5.5
- [ ] **Health check real:** BD con escritura de prueba, Ollama con modelo cargable, Whisper disponible y espacio en disco. Distingue lo imprescindible de lo que solo afecta a la IA.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **`doctor.ps1`:** cubre versión de Windows, RAM, disco, puerto, Ollama, modelos, sqlite-vec, permisos de carpetas, conectividad a `127.0.0.1` y versión de la app; cada fallo con su acción.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Cada fallo de `doctor.ps1`** tiene su entrada en `docs/usuario/que-hacer-si.md` y se ha provocado al menos una vez.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Paquete de diagnóstico** (`-Bundle`): anonimizado por defecto, sin BD ni PDFs, suficiente para resolver sin pedir una segunda ronda de información. Probado con tres fallos provocados y con su contenido revisado.
  - 🤖 `plataforma-entrega` · Opus 5.5

---

## Fase 7 — Seguridad y cumplimiento

### Automatizado

- [ ] **Dependencias:** `pip-audit` y `npm audit` sin vulnerabilidades altas ni críticas.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **SAST:** bandit y Semgrep (reglas de Python, FastAPI y TypeScript) sin hallazgos altos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **DAST:** ZAP baseline contra la app local en `127.0.0.1`.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Secretos:** gitleaks sobre todo el historial, sin secretos en fixtures, artefactos ni logs de CI; los PDFs de `samples/` son sintéticos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Licencias de dependencias** compatibles con distribución comercial bajo licencia anual (sin GPL incompatible en lo que se distribuye).
  - 🤖 `plataforma-entrega` · Opus 5.5

### Revisión STRIDE

Todos los de este bloque: 🤖 `seguridad-ia` · Opus 5.5 → corrige: el agente dueño.

- [ ] **Suplantación:** al no haber autenticación, el límite es la red: el servidor solo escucha en `127.0.0.1`. Si existe modo red local, exige PIN y avisa.
- [ ] **Ataques desde el navegador contra localhost:** comprobación de cabecera `Host` (anti DNS rebinding), `Origin` en peticiones que escriben, sin CORS abierto, token CSRF o cabecera personalizada en mutaciones.
- [ ] **Otros procesos del equipo:** la confirmación de una `PendingAction` no se puede forzar desde el agente ni desde el contenido de un documento.
- [ ] **Manipulación:** triggers de inmutabilidad, cadena de `BillingRecord` sobre JSON canónico, `PendingAction` firmada con HMAC y clave local.
- [ ] **Repudio:** `audit_events` registra emisiones, rectificaciones, cobros y qué propuestas del agente confirmó el usuario.
- [ ] **Divulgación:** logs y bundle sin datos personales; errores sin trazas internas; prompts sin datos de otros clientes de más.
- [ ] **Denegación:** límite de tamaño y páginas en la ingesta, tiempo máximo por PDF, límite de iteraciones del agente, timeout de llamadas a Ollama, cola de ingesta acotada.
- [ ] **Elevación:** subida de ficheros sin ejecución, nombres de fichero saneados, sin rutas controladas por el usuario fuera de las carpetas de la app.
- [ ] **Configuración:** cabeceras de seguridad, CSP sin `unsafe-inline` ni `unsafe-eval` en el build y compatible con el worker de pdf.js, `Permissions-Policy: microphone=(self)`, documentación de la API no expuesta en modo release salvo que se active.

### PDFs no confiables

Un PDF importado es la principal entrada hostil del producto, y se procesa en tres sitios: en el servidor, en el modelo y en el navegador.

- [ ] **Visor en la pantalla de revisión:** `pdfjs-dist` ≥ 4.2.67 (CVE-2024-4367: un PDF con una fuente manipulada ejecuta JavaScript) y `isEvalSupported: false`; el JavaScript embebido no se ejecuta. Prueba con un PDF malicioso de ejemplo.
  - 🤖 `seguridad-ia` · Opus 5.5 (revisa) + `qa-testing` · Opus 5.5 (prueba) → corrige: `arquitecto-vue`
- [ ] **Lectura en el servidor:** pdfplumber corre con límites de tiempo y memoria; un PDF hostil no tumba el proceso ni la cola.
  - 🤖 `seguridad-ia` · Opus 5.5 (revisa) → corrige: `ingeniero-ia`
- [ ] **Servido del fichero:** los PDFs se sirven por ID con `Content-Type` correcto y `X-Content-Type-Options: nosniff`.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`

### Superficie de la API

No hay roles ni cuentas: el equivalente a las pruebas de autorización es recorrer toda la API desde fuera del límite de confianza.

- [ ] **Prueba parametrizada sobre `openapi.json`:** cada ruta que escribe rechaza un `Host` o un `Origin` ajeno y la falta de la cabecera obligatoria. Una ruta nueva queda cubierta sin escribir otra prueba.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Referencias directas:** manipulando IDs y rutas no se llega a ficheros fuera de las carpetas de la app.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Modo red local** (si existe): está desactivado por defecto y cada ruta exige sesión cuando se activa.
  - 🤖 `qa-testing` · Opus 5.5

### Privacidad local: modelos y Ollama

- [ ] **Modelos de Ollama solo locales:** la configuración rechaza modelos con sufijo `-cloud`, que se ejecutan fuera del equipo, y la instalación deja Ollama en modo local (`OLLAMA_NO_CLOUD=1` o `disable_ollama_cloud` en `server.json`; contrastar con la documentación vigente). `doctor.ps1` lo comprueba (RNF-01).
  - 🤖 `seguridad-ia` · Opus 5.5 (revisa) + `plataforma-entrega` · Opus 5.5 (implementa y prueba)
- [ ] **Ollama sin exponer:** `doctor.ps1` avisa si escucha fuera de `127.0.0.1` (variable `OLLAMA_HOST`), también cuando ya estaba instalado antes que Kapataz.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Modelo de Whisper:** se descarga durante la instalación, no al pulsar el micrófono por primera vez, y en ejecución se carga solo de disco (ruta local o `local_files_only=True`). Sin esto fallan RNF-01 y RNF-08.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Tráfico de red:** con una captura durante una sesión completa (consulta, ingesta, voz) no hay conexiones salientes de Kapataz. Las de Ollama, como la búsqueda de actualizaciones, se anotan y se explican en la documentación.
  - 🤖 `plataforma-entrega` · Opus 5.5

### OWASP Top 10 (aplicaciones web, edición 2025)

> Cada categoría tiene una prueba automatizada en `backend/tests/security/` (o en Pester o Playwright cuando corresponde) con el marcador `@pytest.mark.owasp("A0X")`, además del marcador de requisito. `traceability.py --check` falla si alguna categoría se queda sin prueba.

Revisa: 🤖 `seguridad-ia` · Opus 5.5 → corrige: el agente dueño. Automatiza: 🤖 `qa-testing` · Opus 5.5.

| ✓ | Categoría | Riesgo concreto en Kapataz | Mitigación | Ref. | Prueba automatizada |
|---|---|---|---|---|---|
| [ ] | **A01 · Control de acceso roto** (incluye SSRF) | Una web maliciosa abierta en el navegador ataca `localhost` (DNS rebinding, CSRF); descarga de documentos manipulando rutas; la app hace peticiones a URLs que no debe | Escucha solo en `127.0.0.1`; middleware que valida `Host` contra una lista blanca y `Origin` en toda petición que escribe; cabecera personalizada obligatoria en mutaciones; documentos servidos por ID, nunca por ruta; la URL de Ollama solo admite `localhost`; en modo red local, PIN obligatorio | RNF-12, ADR-019 | `test_a01_host_ajeno_rechazado`, `test_a01_origin_ajeno_en_post_403`, `test_a01_path_traversal_404`, `test_a01_ollama_url_externa_rechazada` |
| [ ] | **A02 · Configuración de seguridad incorrecta** | Documentación de la API, modo depuración o CORS abierto en la versión entregada; base de datos legible por otros usuarios del equipo | CSP sin `unsafe-inline`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy: microphone=(self)`, `/docs` desactivado en release, sin CORS; carpeta de datos con ACL solo para el usuario | ADR-013 | `test_a02_cabeceras_seguridad`, `test_a02_docs_desactivado_en_release`, ZAP baseline contra la app local, Pester `ACL de la carpeta de datos` |
| [ ] | **A03 · Fallos en la cadena de suministro de software** | Dependencia comprometida; instalador de Ollama o uv alterado; acciones de CI secuestradas | `uv.lock` con hashes y `npm ci`; `pip-audit` y `npm audit`; SBOM CycloneDX en cada release; acciones de GitHub fijadas por SHA; `install.ps1` verifica la suma SHA-256 de todo lo que descarga y aborta si no coincide | ADR-022 | Job de CI `sbom-y-auditoria`; Pester `install aborta si la suma no coincide` |
| [ ] | **A04 · Fallos criptográficos** | Firma de `PendingAction` falsificable; clave guardada en claro junto al código; comparación de firmas vulnerable a tiempo | Clave HMAC de 256 bits generada con `secrets` en el primer arranque, guardada en `%LOCALAPPDATA%` con ACL de usuario; `hmac.compare_digest`; SHA-256 para la cadena de registros; copias de seguridad cifradas opcionalmente con contraseña (AES-GCM, `cryptography`); ninguna criptografía casera | ADR-018 | `test_a04_firma_alterada_rechazada`, `test_a04_clave_no_en_repo`, regla Semgrep `comparacion-de-firma-con-==` |
| [ ] | **A05 · Inyección** | SQL construido con cadenas; sintaxis de `MATCH` de FTS5 inyectada desde el chat; **fórmulas en la exportación CSV/Excel** (`=HYPERLINK(...)` en el nombre de un cliente); **marcado de ReportLab** inyectado en conceptos (`<link>`, `<img>`); XSS en Vue; inyección en los scripts de PowerShell | Consultas parametrizadas, sin `text()` con f-strings; los términos de FTS5 se escapan como frases; celdas que empiezan por `= + - @ \t \r` se prefijan con `'`; todo texto de usuario se escapa antes de pasar a `Paragraph`; prohibido `v-html`; los scripts no usan `Invoke-Expression` | RF-FA-09, RF-PR-06 | `test_a05_fts_sintaxis_maliciosa`, `test_a05_csv_formula_neutralizada`, `test_a05_reportlab_marcado_escapado`, regla ESLint `vue/no-v-html`, regla Semgrep `sqlalchemy-text-fstring`, PSScriptAnalyzer `AvoidUsingInvokeExpression` |
| [ ] | **A06 · Diseño inseguro** | El agente puede emitir facturas por su cuenta; una factura se puede editar después de emitida | Modelo de amenazas antes del código (Bloque 0); `PendingAction` con confirmación humana; inmutabilidad en dominio **y** en BD; rectificativas | ADR-012, ADR-018, RN-04, RN-F-02 | Escenarios Gherkin «factura emitida inmutable» e «inyección en un PDF» |
| [ ] | **A07 · Fallos de autenticación** | No aplica en modo local (sin cuentas). Aplica al modo red local opcional: PIN adivinable por fuerza bruta, sesión robable | PIN de 6 dígitos mínimo, HTTPS en ese modo, bloqueo creciente tras fallos, cookie de sesión `HttpOnly` + `SameSite=Strict`, caducidad por inactividad; el modo red local está desactivado por defecto | RNF-12 | `test_a07_pin_bloqueo_creciente`, `test_a07_cookie_flags`, `test_a07_red_local_desactivada_por_defecto` |
| [ ] | **A08 · Fallos de integridad de software y datos** | Cadena de facturación alterada; copia de seguridad manipulada antes de restaurar; actualización sustituida; deserialización insegura | `verify-billing-chain` al arrancar; manifiesto con huellas en cada `.kapataz-backup` y rechazo si no cuadra; `install.ps1 -Update` verifica la suma de la release; prohibidos `pickle`, `yaml.load` y `eval` | RN-F-07, RF-CF-03, ADR-014 | `test_a08_cadena_alterada_detectada`, `test_a08_backup_manipulado_rechazado`, Pester `update rechaza release alterada`, regla Semgrep `no-pickle` |
| [ ] | **A09 · Fallos de registro y alertas** | Una alteración de la cadena pasa desapercibida; los logs filtran NIF o nombres | `audit_events` para toda operación fiscal y confirmación del agente; aviso visible en la interfaz si la verificación de la cadena falla; `doctor.ps1` lo reporta; filtro de structlog que enmascara NIF, emails y teléfonos | ADR-015 | `test_a09_aviso_si_cadena_rota`, `test_a09_logs_sin_datos_personales` (recorre los logs de la suite E2E buscando patrones de NIF, email y teléfono) |
| [ ] | **A10 · Manejo incorrecto de condiciones excepcionales** | Una excepción al verificar una firma deja pasar la acción; un error a mitad de emisión consume número; trazas internas en la respuesta | Fallo cerrado: cualquier excepción en una verificación equivale a rechazo; transacción por caso de uso con reversión; `problem+json` sin trazas; schemathesis con datos aleatorios | ADR-009, RN-F-01 | `test_a10_verificacion_falla_cerrada`, `test_a10_emision_fallida_no_consume_numero`, schemathesis sin respuestas 500 |

### OWASP Top 10 para aplicaciones LLM (edición 2025)

Revisa: 🤖 `seguridad-ia` · Opus 5.5 → corrige: `ingeniero-ia`. Automatiza: 🤖 `qa-testing` · Opus 5.5. Las pruebas que necesitan modelo real llevan además el marcador `llm` y se ejecutan en la Fase 4.

| ✓ | Categoría | Riesgo concreto en Kapataz | Mitigación | Ref. | Prueba automatizada |
|---|---|---|---|---|---|
| [ ] | **LLM01 · Inyección de instrucciones** | Un PDF importado o un concepto escrito por un cliente contiene órdenes para el agente | Contenido recuperado delimitado y marcado como datos; nunca concatenado al prompt de sistema; herramientas de escritura solo como propuesta; lista blanca de herramientas por turno | RN-05, ADR-019 | Batería de 20 casos en `evals/security/` (`pytest -m llm`); `test_llm01_contenido_recuperado_delimitado` (sin modelo, comprueba el prompt construido) |
| [ ] | **LLM02 · Divulgación de información sensible** | El agente vuelca NIF, direcciones o importes de otros clientes que no venían a cuento; las trazas guardan contenido de documentos | Herramientas que devuelven solo los campos necesarios para la pregunta; NIF fuera del contexto salvo que la pregunta lo requiera; `agent_runs` guarda parámetros sin datos personales | ADR-015, RGPD | `test_llm02_herramientas_minimizan_campos`, `test_llm02_agent_runs_sin_datos_personales` |
| [ ] | **LLM03 · Cadena de suministro** | Modelo descargado de un origen no oficial o sustituido; **licencia del modelo incompatible con la venta bajo licencia anual** | Solo la biblioteca oficial de Ollama; nombre, etiqueta y digest fijados en la configuración de cada perfil; `doctor.ps1` verifica el digest; los modelos de Whisper, que no vienen de Ollama, con repositorio y revisión fijados; licencia de cada modelo candidato revisada y anotada en el ADR-005 antes de elegirlo | ADR-005, ADR-022 | `test_llm03_digest_modelo_coincide`; casilla de licencia en el informe de evaluación |
| [ ] | **LLM04 · Envenenamiento de datos y modelos** | Una factura importada con un precio absurdo (o un error de extracción) contamina el «precio habitual» y los presupuestos futuros; un PDF diseñado para aparecer en todas las búsquedas | Solo cuentan documentos **revisados y aprobados**; los precios de referencia excluyen atípicos (mediana y MAD); muestras mínimas para dar un precio; el usuario puede excluir un documento y se recalcula todo; límite de fragmentos por documento en los resultados | RN-07, RN-08, ADR-023 | `test_llm04_atipico_no_altera_mediana`, `test_llm04_documento_en_revision_no_cuenta`, `test_llm04_excluir_documento_recalcula` |
| [ ] | **LLM05 · Manejo inadecuado de la salida** | El texto del modelo se interpreta como HTML; parámetros de herramienta no validados llegan a SQL; enlaces inventados | Salida renderizada como texto (o Markdown saneado con DOMPurify si se activa); parámetros validados con Pydantic antes de ejecutar; enlaces solo a IDs que devolvió una herramienta; cifras renderizadas desde el resultado de la herramienta | RN-02, RF-CO-03 | `test_llm05_parametros_invalidos_rechazados`, `test_llm05_enlace_inexistente_descartado`, Vitest `chat no renderiza HTML del modelo` |
| [ ] | **LLM06 · Agencia excesiva** | El agente emite, rectifica o registra cobros sin que el usuario lo vea | Ninguna herramienta de escritura ejecuta: todas devuelven `PendingAction` firmada; ninguna herramienta borra; límite de iteraciones; la confirmación solo llega desde la interfaz | RN-04, ADR-018 | `test_llm06_ninguna_herramienta_escribe_directamente` (recorre el registro de herramientas), `test_llm06_pending_action_caducada` |
| [ ] | **LLM07 · Fuga del prompt de sistema** | Alguien obtiene el prompt de sistema | El prompt no contiene secretos, claves ni datos del usuario, así que su fuga tiene impacto bajo; se documenta como riesgo aceptado | ADR-019 | `test_llm07_prompt_sin_secretos` (busca claves, rutas y datos personales en los prompts versionados) |
| [ ] | **LLM08 · Debilidades de vectores y embeddings** | Fragmentos de un documento excluido o en revisión siguen apareciendo en búsquedas; cambio de modelo de embeddings con dimensiones distintas mezcla vectores incompatibles; filtros de búsqueda aplicados por el modelo en lugar de por SQL | Al excluir o borrar un documento se purgan sus fragmentos de FTS5 y de sqlite-vec en la misma transacción; solo se indexan documentos aprobados; el modelo de embeddings y su dimensión se guardan con el índice y un cambio obliga a reindexar; los filtros (cliente, fechas, tipo) se aplican en SQL | RN-08, ADR-007 | `test_llm08_documento_excluido_no_aparece`, `test_llm08_cambio_modelo_exige_reindexado`, `test_llm08_filtros_en_sql` |
| [ ] | **LLM09 · Desinformación** | El agente presenta como «precio habitual» una mediana de dos facturas; da por cierta una afirmación fiscal o legal | Cada precio va con número de muestras y rango; con menos de 3 muestras se avisa y no se propone automáticamente; cifras siempre desde herramientas con fuentes; ante preguntas fiscales o legales el agente informa en términos generales y remite a la gestoría | RN-02, RN-06, RN-07, RN-09 | `test_llm09_precio_incluye_muestras_y_rango`, `test_llm09_pocas_muestras_avisa`; evaluación `pregunta fiscal remite a gestoría` (`-m llm`) |
| [ ] | **LLM10 · Consumo ilimitado** | Un bucle de herramientas, un PDF de miles de páginas o muchas peticiones simultáneas dejan el equipo sin memoria | Límite de iteraciones, tokens de salida y tiempo por turno; límites de tamaño y páginas en la ingesta; cola única hacia Ollama; Whisper con duración máxima de audio | ADR-006 | `test_llm10_bucle_cortado_por_limite`, `test_llm10_pdf_excesivo_rechazado`, `test_llm10_audio_excesivo_rechazado` |

### RGPD

Todos los de este bloque: 🤖 `seguridad-ia` · Opus 5.5.

- [ ] **Minimización:** cada campo personal es necesario para presupuestar o facturar.
- [ ] **Datos de terceros:** los clientes del profesional se tratan solo en su equipo; nada sale salvo la opción de voz externa, con aviso explícito.
- [ ] **Derechos:** exportar y borrar los datos de un cliente concreto, respetando la conservación obligatoria de facturas emitidas.
- [ ] **Conservación:** las facturas emitidas no se purgan; la purga de trazas del agente y logs es configurable.
- [ ] **Sin comunicaciones a terceros:** ni fuentes desde CDN, ni telemetría, ni comprobaciones de versión sin consentimiento.

### Facturación y preparación para Verifactu

- [ ] **Inmutabilidad real**, numeración sin huecos y rectificativas verificadas en código y en BD.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **Marca de demostración** presente en todo PDF de factura mientras no haya perfil fiscal conforme (RN-F-09), y sin forma de quitarla por configuración en esta versión.
  - 🤖 `seguridad-ia` · Opus 5.5 (verifica) + `backend-fastapi` · Opus 5.5 (prueba)
- [ ] **Documento de brecha Verifactu** actualizado y contrastado con la normativa vigente.
  - 🤖 `seguridad-ia` · Opus 5.5 + `arquitecto-python` · Opus 5.5
- [ ] **Licencia caducada** (ADR-016): no impide consultar ni exportar los datos propios.
  - verifica: 🤖 `seguridad-ia` · Opus 5.5
  - prueba: 🤖 `plataforma-entrega` · Opus 5.5
- [ ] 👤 **Validación fiscal** con una gestoría o asesor antes de usar las facturas en real. Fuera del alcance de los agentes.

**Límite de cumplimiento:** Kapataz v1 usa un adaptador nulo de Verifactu y sus facturas son de demostración. Este plan no certifica cumplimiento fiscal ni autoriza su uso real.

---

## Fase 8 — Rendimiento

> Equipo de referencia del perfil `estandar`: 16 GB de RAM, CPU de 6 núcleos reciente, sin GPU. Anota el equipo real en el informe. Son objetivos de una instancia local de un solo usuario: no hay pruebas de carga con usuarios concurrentes.

- [ ] **Latencia del chat:** primera respuesta visible < 3 s y completa < 15 s en consultas de una herramienta (RNF-04); p50 y p95 sobre el dataset del agente, con el modelo ya cargado y también en frío.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Ingesta:** < 30 s por PDF de una página (RNF-05); importación de la demo completa medida.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Reindexado** completo de la demo < 2 min en perfil `estandar`.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Arranque** del servidor < 5 s (RNF-03); memoria en reposo medida con y sin modelos cargados.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **SQLite:** `EXPLAIN QUERY PLAN` sobre las consultas de las herramientas; ninguna sin índice; prueba con 10 años de datos sintéticos (≈ 5.000 facturas).
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Frontend:** JS inicial ≤ 200 KB gzip, con pdf.js cargado aparte y solo en la pantalla de revisión; LCP ≤ 2 s en local; listados de facturas virtualizados a partir de 500 filas.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Perfil `ligero`:** la app sigue siendo usable en 8 GB (sin swap continuo), con Ollama y Whisper cargados a la vez; si no, se documenta el límite real.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Resistencia:** 4 h de uso simulado (consultas, ingestas y transcripciones alternas) sin fuga de memoria en el proceso Python.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 9 — Datos y base de datos

- [ ] **Migraciones:** todas con `downgrade()` probado; ejecución sobre una BD de la versión anterior con datos.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Triggers tras migrar:** el modo batch de Alembic recrea tablas y puede perder triggers e índices. Tras cada migración se comprueba que siguen los de inmutabilidad y que las tablas FTS5 y vectoriales conservan sus datos.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Invariantes en el esquema:** triggers de inmutabilidad, unicidad de serie + año + número, y claves foráneas comprobadas (`PRAGMA foreign_keys=ON` en **cada** conexión).
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Transacción de emisión:** se comprueba que llega a SQLite un `BEGIN IMMEDIATE` real, porque ni el driver `sqlite3` ni SQLAlchemy lo emiten por defecto, y que `busy_timeout` está configurado.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **sqlite-vec en Windows:** la extensión carga con el Python que instala uv; si no carga, entra el fallback NumPy con los mismos resultados y `doctor.ps1` avisa.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Integridad:** `PRAGMA integrity_check` en `doctor.ps1`.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Copias de seguridad:** fichero `.kapataz-backup` con la API de backup de SQLite (no copia de fichero en caliente), PDFs propios y manifiesto con huellas; restauración verificada.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Copia dañada:** una copia corrupta o manipulada se rechaza sin tocar los datos existentes, y un fallo a mitad de restauración no destruye nada.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Simulacro de restauración** en Windows Sandbox limpio a partir de un backup: las facturas, los documentos, la cadena de registros y el siguiente número siguen intactos. Se anota el tiempo.
  - 🤖 `plataforma-entrega` · Opus 5.5

---

## Fase 10 — Instalación y entrega

- [ ] **CI por etapas**, falla si algo falla, en `windows-latest`; ningún check se ha omitido por cambios en rutas o en nombres de workflow.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **PRs de bloque:** todos integrados con sus checks requeridos en verde; las excepciones aprobadas están en el registro.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **`install.ps1`:**
  - idempotente (dos ejecuciones seguidas);
  - comprueba requisitos antes de tocar nada;
  - funciona en Windows PowerShell 5.1 y en PowerShell 7;
  - funciona con un nombre de usuario con espacios y tildes (en VM);
  - funciona en Windows 10 y en Windows 11 (Windows 10 en VM);
  - no cambia la política de ejecución global;
  - solo pide privilegios de administrador para instalar Ollama, si falta;
  - códigos de salida documentados.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Interrupción:** cortar `install.ps1` durante la descarga de modelos deja un estado del que la siguiente ejecución se recupera.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Actualización** (`-Update`): copia previa verificada como paso bloqueante, salto entre versiones no consecutivas y vuelta atrás automática.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Desinstalación** limpia que respeta la elección de conservar datos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Antivirus:** la instalación y el arranque no disparan Windows Defender (y, si se usa PyInstaller, el ejecutable tampoco).
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Artefacto de release:** sin datos de usuario, secretos, PDFs reales ni modelos no autorizados; SBOM incluido.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] 👤 **Prueba en un Windows real que no sea tu equipo de desarrollo**, idealmente de alguien no técnico siguiendo solo la guía. Anota el resultado y lo que tarda.

---

## Fase 11 — Documentación

- [ ] **Documentación de usuario:** instalación, uso, copia de seguridad, desinstalación y «qué hacer si…» para cada fallo previsible.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **Comandos de la documentación** copiados y ejecutados tal cual.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **README y caso de estudio:** cifras sacadas de `docs/04-evaluacion-ia.md`, sin datos inventados; aviso legal de facturación en modo demostración.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **Limitaciones documentadas:** Verifactu sin implementar, uso fiscal real no permitido y qué funciones necesitan Ollama.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **ADR al día:** ninguna decisión estructural sin ADR y ninguno en «Propuesto».
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Contrato:** `openapi.json` coincide exactamente con la implementación.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Modelo de amenazas** actualizado con lo encontrado en la Fase 7.
  - 🤖 `seguridad-ia` · Opus 5.5

---

## Fase 12 — Accesibilidad y UX

- [ ] **Contraste** WCAG 2.2 AA medido en todas las parejas de tokens, con prueba automatizada.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] **axe:** `@axe-core/playwright` sin violaciones críticas ni graves en todas las vistas.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Teclado:** flujo completo (preguntar, revisar extracción, crear presupuesto, emitir) sin ratón; foco visible.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Móvil:** vistas principales usables a 360 px; objetivos táctiles ≥ 44 px; botón de micrófono alcanzable con el pulgar.
  - 🤖 `arquitecto-vue` · Sonnet 5.5 + `ui-ux` · Sonnet 5.5
- [ ] **Lectores de pantalla:** regiones vivas en el chat y en el progreso de ingesta; tablas de importes con encabezados asociados.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **i18n:** ningún literal en componentes; fechas e importes en formato español.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Estados del micrófono:** inactivo, escuchando, transcribiendo y error se distinguen sin depender solo del color.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] **Coherencia visual** entre pantallas y PDFs, con importes idénticos en ambos; `prefers-reduced-motion` respetado; modo oscuro completo.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] 👤 **Prueba con un usuario de oficio real:** que cree un presupuesto por voz y lo convierta en factura sin ayuda, con ruido de fondo y en un equipo modesto. Anota dónde duda.

---

## Fase 13 — Revisión final

- [ ] **Revisión del diff completo** de la release contra la Definición de Terminado.
  - 🤖 `revisor-codigo` · Opus 5.5 → corrige: el agente dueño
- [ ] **Pasada final de seguridad y cumplimiento** sobre lo corregido.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **Re-revisión** de cada hallazgo corregido por el mismo agente que lo detectó; cada corrección lleva su prueba de regresión.
- [ ] **Release:** versión, changelog, artefactos e instrucciones de vuelta atrás comprobados.
  - 🤖 `plataforma-entrega` · Opus 5.5

---

## ✅ Criterios de salida

- [ ] Huecos de «Antes de empezar» cerrados.
- [ ] Todos los PR de bloque integrados con CI, seguridad y revisión en verde.
- [ ] `traceability.py --check` en verde: ningún requisito ni categoría OWASP sin prueba.
- [ ] Calidad de backend, frontend y PowerShell en verde; build correcto.
- [ ] Umbrales: cobertura (90 / 80 / 70 %), mutación ≥ 80 % en `domain/billing`, suite unitaria < 10 s.
- [ ] Métricas de IA cumplidas en perfil `estandar`: extracción ≥ 95 %, herramienta ≥ 90 %, parámetros ≥ 90 %, recall@5 ≥ 0,85, **0 cifras no procedentes de herramientas**, 0 fuentes inventadas y 0 escrituras sin confirmación en la batería de inyección.
- [ ] Objetivos de rendimiento RNF-02 a RNF-05 medidos y cumplidos en perfil `estandar`.
- [ ] **0 hallazgos 🔴 CRÍTICO ni 🟠 ALTO** de `seguridad-ia`.
- [ ] **0 hallazgos 🔴 BLOQUEANTE** de `revisor-codigo`.
- [ ] Numeración concurrente, inmutabilidad y cadena de registros verificadas.
- [ ] Sin conexiones salientes de Kapataz y funcionamiento comprobado sin red.
- [ ] Backup restaurado y actualización con vuelta atrás probados.
- [ ] Instalación limpia en Windows Sandbox en < 15 min y `doctor.ps1` en verde.
- [ ] 👤 Prueba en Windows real de terceros superada.
- [ ] 👤 Prueba con usuario de oficio realizada y hallazgos registrados.
- [ ] 👤 Antes de cualquier uso fiscal real: Verifactu implementado y validación de gestoría (fuera del alcance de esta release).

---

## Registro de hallazgos

| # | Fase / PR | Descripción y evidencia | Severidad | Detecta | Corrige | Estado |
|---|---|---|---|---|---|---|
| 1 |  |  |  | `agente` | `agente` | Abierto / Corregido / Re-revisado |
