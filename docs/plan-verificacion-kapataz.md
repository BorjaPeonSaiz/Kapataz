# Plan de verificación pre-release — Kapataz

> **Producto:** servicio web de pago con IA para autónomos de oficio, en portátil y móvil: consulta del histórico, presupuestos y facturas por texto o voz.
>
> **Stack:** Python 3.12 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL (RLS, pgvector) · API de Claude · bucle de agente propio · Presidio + spaCy · fastembed · pdfplumber · Tesseract · ReportLab · faster-whisper · procrastinate · Stripe · Vue 3 + Vite + TypeScript + Tailwind + Pinia · PWA · pdf.js · Docker Compose · Caddy.
>
> **Herramientas:** ruff, mypy `--strict`, import-linter, bandit, pip-audit, Semgrep, gitleaks, Trivy, ZAP, ShellCheck, pytest, pytest-cov, hypothesis, mutmut, schemathesis, freezegun, vue-tsc, ESLint, Prettier, Vitest, Playwright, axe-core, npm audit, k6, GitHub Actions.
>
> **Observabilidad:** structlog JSON, `/api/health`, métricas básicas, monitor externo de disponibilidad, alertas de errores y de gasto de IA, `agent_runs`, `audit_events`, `ai_usage`.
>
> **Despliegue:** Docker Compose en un VPS de la UE, con staging y producción separados; solo Caddy se expone a internet. CI en `ubuntu-latest` con PostgreSQL real y `FakeLlm` determinista; CI no llama a la API de Claude (ADR-008).
>
> **Cómo leer cada tarea:** `🤖 agente · Modelo`. Cuando la detecta un agente de solo lectura, se indica también quién corrige: `→ corrige: agente`.
>
> **Severidades:**
> - `revisor-codigo`: 🔴 BLOQUEANTE · 🟠 IMPORTANTE · 🟡 MENOR
> - `seguridad-ia`: 🔴 CRÍTICO · 🟠 ALTO · 🟡 MEDIO · ⚪ BAJO

Este es el plan que se ejecuta antes de una release. Es la **Parte II** de [`00-plan-maestro.md`](./00-plan-maestro.md). Los requisitos y umbrales salen de `docs/01-especificacion.md` y de los ADR aceptados: si este plan los contradice, manda la especificación y se corrige el plan.

---

## Reparto de agentes y modelos

| Agente | Papel en la verificación | Modelo | Modo |
|---|---|---|---|
| `arquitecto-python` | Reglas de negocio, pureza hexagonal, ADR | **Opus 5.5** | Escritura |
| `backend-fastapi` | Casos de uso, API, migraciones, PostgreSQL, pagos, logs | **Opus 5.5** | Escritura |
| `ingeniero-ia` | Agente, prompts, extracción, RAG, voz, evaluaciones | **Opus 5.5** | Escritura |
| `qa-testing` | Pirámide de pruebas, trazabilidad, E2E, rendimiento | **Opus 5.5** | Escritura |
| `plataforma-entrega` | CI, Docker, despliegue, copias, observabilidad | **Opus 5.5** | Escritura |
| `arquitecto-vue` | SPA, estado, streaming, voz en cliente, i18n | **Sonnet 5.5** | Escritura |
| `ui-ux` | Tokens, contraste, estados, coherencia visual | **Sonnet 5.5** | Escritura |
| `documentacion-portafolio` | README, docs de usuario, caso de estudio | **Sonnet 5.5** | Escritura |
| `seguridad-ia` | STRIDE, OWASP, aislamiento, pagos, RGPD, facturación | **Opus 5.5** | Solo lectura |
| `revisor-codigo` | Definición de Terminado, duplicación, estilo | **Opus 5.5** | Solo lectura |
| 👤 **Tú** | Móviles reales, criterio de negocio, validación fiscal y legal | — | — |

### Criterio de modelos

- **Opus 5.5 para el criterio:** donde un error acaba en una factura mal numerada, un importe mal calculado, un agente que obedece a un PDF o datos de un cliente visibles para otro.
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

- Cada bloque (0–12) va en su rama `bloque-NN-nombre` y en su **propio PR** contra `main`, con código, documentación y pruebas, y con los requisitos afectados enlazados.
- Antes de pedir revisión se ejecutan las pruebas del bloque, su criterio de terminado y la Definición de Terminado, y el PR deja `HANDOFF.md` al día.
- Lo que no corre en CI (evaluaciones con `pytest -m llm`, pruebas en móviles reales) se ejecuta aparte y el PR anota resultado, modelo, versión del prompt, coste y fecha.
- Para integrar deben estar en verde el CI de GitHub, las comprobaciones de seguridad (`pip-audit`, `npm audit`, bandit, Semgrep, gitleaks y Trivy, sin hallazgos altos ni críticos) y la revisión de `revisor-codigo`.
- Un check fallido o pendiente bloquea la integración. Una excepción exige justificación en el PR, con riesgo, mitigación y tu aprobación. No se exceptúan defectos críticos de seguridad ni invariantes fiscales.
- El Bloque 0 solo aporta documentación: se comprueba en local y se integra con tu visto bueno. El Bloque 1 crea los workflows y la protección de `main`, y su propio PR ya debe pasarlos.
- Desde la 1.0.0, cada cambio de la app lleva además versión, changelog y etiqueta (ADR-032). Este plan completo se repite antes de cada MAJOR; en una MINOR, solo las fases afectadas.

---

## Antes de empezar: decisiones abiertas

Este plan comprueba comportamientos que todavía no están decididos. Hay que cerrarlos antes de la Fase 1: `arquitecto-python` propone y tú decides.

| # | Decisión | Dónde aparece | Qué hace falta |
|---|---|---|---|
| 1 | **Consulta al asesor:** (a) obligación actual como productor; (b) apoderamiento de cada cliente; (c) qué ocurre con los datos tras los 90 días de solo lectura y qué hay que conservar tras una baja; (d) papel de Anthropic y Stripe en el contrato de encargo; (e) tratamiento de anticipos y fases en la factura final | §1.4, RF-VF-07, RN-12, RF-AC-06, ADR-029, ADR-033 | Hacerla antes del lanzamiento. Puede cambiar el diseño |
| 2 | **Proveedor de Verifactu** | Bloque 12, ADR-012 | Elegirlo con precios y condiciones reales |
| 3 | **WER sin umbral** | Bloque 9 | Se mide y se anota. No se declara aprobado ni suspenso mientras la especificación no fije un valor |
| 4 | **El escenario «Extracción que no cuadra»** no indica el IVA: la diferencia de 90,00 € solo sale con el 21 % | §3.5 | Añadir el tipo de IVA al escenario |

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
| 8 | 7 · Seguridad (STRIDE, OWASP, aislamiento, pagos, RGPD, facturación) | seguridad-ia, qa-testing |
| 9 | 6 · Observabilidad y diagnóstico | backend, plataforma |
| 10 | 8 · Rendimiento | qa-testing, ingeniero-ia, arquitecto-vue |
| 11 | 9 · Datos y base de datos | backend, plataforma |
| 12 | 10 · Despliegue y entrega | plataforma, 👤 |
| 13 | 11 · Documentación | documentacion-portafolio, arquitecto |
| 14 | 12 · Accesibilidad, móvil y UX | ui-ux, arquitecto-vue, qa-testing, 👤 |
| 15 | 13 · Revisión final | revisor-codigo, seguridad-ia |

La Fase 4 usa Claude real y cuesta dinero: estima el coste y apruébalo antes de lanzarla.

---

## Fase 0 — Preparación

- [ ] **Congelar el código:** rama `release/1.0` con la candidata `1.0.0-rc.N`; árbol de trabajo limpio y lista de los PR y bloques incluidos. Cada corrección de la verificación genera una candidata nueva.
  - 🤖 hilo principal · Sonnet 5.5
- [ ] **Decisiones cerradas:** la tabla «Antes de empezar» está resuelta y todo ID citado en este plan existe en la especificación o en el catálogo de ADR.
  - 🤖 `arquitecto-python` · Opus 5.5 + 👤
- [ ] **Staging limpio** con datos sintéticos versionados que incluyan los casos límite: varias cuentas, suscripciones activas y terminadas, clientes ambiguos, inversión del sujeto pasivo, retenciones, rectificativas, PDFs con errores sembrados y PDF trampa. Ningún dato real.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Matriz de trazabilidad** con `cd backend && uv run python tools/traceability.py --check`, cruzada con los RF, RN y RNF de `docs/01-especificacion.md`.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Inventario de endpoints:** cruzar las rutas de FastAPI con `docs/api/openapi.json`. Una ruta sin contrato o un contrato sin ruta es un hallazgo.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Despliegue limpio** en un servidor vacío siguiendo **solo** `docs/operacion/`, terminando con `/api/health` en verde.
  - 🤖 `plataforma-entrega` · Opus 5.5

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
- [ ] **Precios:** cada precio propuesto indica de dónde sale, con muestras y rango; sin origen, la línea queda sin precio y marcada (RN-06, RN-07).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Voz:** RF-VO cubiertos; el audio no sale de nuestro servidor y se borra al transcribir; la transcripción es editable antes de enviarse.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Frontend:** cada RF con interfaz tiene su pantalla; borrador y emitida se distinguen sin leer; la emisión pide confirmación diferenciada; el frontend no recalcula totales.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Configuración:** asistente de primer arranque, catálogo editable, exportación de datos y modo demostración (RF-CF).
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Cuentas, pagos y móvil:** RF-AC, RF-PG, RF-MO y RF-UC completos.
  - 🤖 `backend-fastapi` · Opus 5.5 + `arquitecto-vue` · Sonnet 5.5
- [ ] **Superadministración:** RF-SA completos; un cliente no tiene ningún ajuste de modelo.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Verifactu:** RF-VF completos; `RegistroFacturacionPort` no se salta en ningún camino de emisión.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Escenarios Gherkin** de §3.5 automatizados y en verde.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 2 — Calidad de código

### Automatizado

- [ ] **Backend:** `ruff check`, `ruff format --check`, `mypy --strict` y `lint-imports` en verde; cada `# type: ignore` y `# noqa` lleva justificación.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **CI:** las etapas de lint y unitarias tardan menos de 10 minutos; es determinista y no llama a la API de Claude ni a la de Stripe.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Scripts e imágenes:** ShellCheck sin avisos en `deploy/`; imágenes sin root y fijadas por digest.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Frontend:** `npm run type-check && npm run lint && npm run test:unit && npm run build` en verde.
  - 🤖 `arquitecto-vue` · Sonnet 5.5

### Revisión de arquitectura

- [ ] **Pureza del dominio:** `domain/` no importa FastAPI, SQLAlchemy, el SDK de Anthropic, Stripe, pdfplumber, ReportLab ni nada de `infrastructure`.
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
- [ ] **Contexto de cuenta:** ningún repositorio, herramienta ni tarea accede a datos sin cuenta fijada.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Puerta hacia Claude:** `LlmPort` solo acepta `SanitizedPrompt`; no existe otro camino hacia el SDK de Anthropic.
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Modelo:** ningún nombre de modelo fijado en el código; todo se lee de `platform_settings`.
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

- [ ] **Redondeo:** propiedades con hypothesis; casos frontera (0,005 €, cantidades decimales, descuentos del 100 %); la suma de bases y cuotas cuadra con el total, y la de las fases, con el presupuesto.
- [ ] **Fiscalidad:** IVA 21/10/4 %, mezcla de tipos en una factura, inversión del sujeto pasivo con cuota cero y su mención, retención del 15 % y del 7 %.
- [ ] **NIF, NIE y CIF:** formatos válidos e inválidos y dígito de control.
- [ ] **Datos obligatorios:** falta un dato de RN-F-06 y la factura no se emite.

**Numeración e inmutabilidad**

- [ ] **Numeración concurrente:** 20 emisiones en paralelo con procesos distintos sobre PostgreSQL real, en una cuenta y en varias a la vez; sin huecos ni duplicados.
- [ ] **Series independientes:** `F`, `R` y `P` numeran por separado en cada cuenta; el número se asigna al emitir, no al crear el borrador.
- [ ] **Cambio de año:** la primera factura del año reinicia la numeración; una emisión el 31/12 a las 23:59:59 y otra el 01/01 a las 00:00:00.
- [ ] **Fecha anterior:** se rechaza emitir con fecha anterior a la última de la serie.
- [ ] **Emisión fallida:** no consume número ni deja un `BillingRecord` huérfano.
- [ ] **Inmutabilidad por SQL directo:** `UPDATE` y `DELETE` sobre una factura emitida fallan por trigger.
- [ ] **Cadena de registros:** se altera un `billing_record` por SQL y `verify-billing-chain` lo detecta.
- [ ] **Rectificativa:** por diferencias y por sustitución, con referencia y motivo.

**Presupuestos y cobros**

- [ ] **Estados:** borrador → enviado → aceptado, rechazado o caducado, y facturado parcialmente → facturado; la caducidad se calcula con `Clock`.
- [ ] **Versiones:** modificar un enviado crea una versión nueva y conserva la anterior.
- [ ] **Conversión:** un presupuesto aceptado genera un borrador de factura, completo o de una fase, y mantiene el vínculo; uno no aceptado no se convierte.
- [ ] **Fases:** por porcentaje, importe y líneas, con varios tipos de IVA, retención e inversión del sujeto pasivo; cada fase lleva su número y la fase final factura lo pendiente al céntimo (RN-F-12).
- [ ] **Límite de lo facturado:** una fase que supera lo pendiente se rechaza; dos borradores a la vez no pueden pasarse del total; eliminar un borrador libera su importe; una rectificativa ajusta lo facturado (RN-F-11).
- [ ] **Nueva versión del presupuesto:** una ampliación sube lo pendiente; una versión por debajo de lo ya facturado se rechaza.
- [ ] **Cobros:** pendiente, parcial y completo, con fecha y forma de pago; el estado de cobro no toca los datos fiscales.
- [ ] **Cobro superior al pendiente:** se rechaza con el importe restante, también cuando lo propone el agente (RN-F-10).
- [ ] **Exportación:** libro de facturas en CSV y Excel por periodo; los importes cuadran con los de la aplicación.

**Ingesta**

- [ ] **PDFs problemáticos:** duplicado por hash, cifrado, escaneado, de 200 páginas, malformado, con total incorrecto y con compresión diseñada para agotar memoria.
- [ ] **Subida:** varios PDF a la vez y desde el móvil; una conexión cortada a mitad no deja documentos a medias. El mismo PDF en dos cuentas distintas no se considera duplicado.
- [ ] **Revisión:** ningún documento con baja confianza o que no cuadra cuenta para las consultas hasta aprobarse (RN-08).
- [ ] **Clientes:** deduplicación por NIF y fusión por similitud solo con confirmación del usuario.

**Agente**

- [ ] **Conversación:** cliente ambiguo, pregunta sin datos, periodo implícito, herramienta desconocida, pregunta fiscal (RN-09) y bucle infinito cortado por el límite.
- [ ] **Precios:** un atípico no altera la mediana; con menos de 3 muestras se avisa y no se propone (RN-07).
- [ ] **PendingAction:** caducada, alterada (firma inválida) y confirmada dos veces (idempotencia); doble clic en Confirmar emite una sola factura.
- [ ] **Divergencia del índice:** un documento borrado o excluido a mano en `chunks` se detecta y el reindexado lo corrige.

**Validez legal y Verifactu**

- [ ] **Factura completa:** el PDF contiene todos los datos obligatorios en cada combinación de IVA, retención e inversión del sujeto pasivo.
- [ ] **Sin marca en cuentas reales:** una factura de una cuenta real no lleva marca de demostración; una del espacio de demostración siempre la lleva (RN-F-09).
- [ ] **Registros:** alta y anulación con el formato y la huella oficiales, comprobados con los ejemplos de la AEAT.
- [ ] **QR:** se lee y apunta a los datos correctos.
- [ ] **Envío:** aceptado en el entorno de pruebas de la AEAT mediante el proveedor; reintentos y rechazos gestionados, y el usuario ve el estado de cada registro.
- [ ] **Autorización:** sin ella no se emite una factura real; el resto de la app funciona (RF-VF-07).
- [ ] **Exportación de registros** completa y solo de esa cuenta.

**Aislamiento entre cuentas**

- [ ] **Por la API:** cada ruta se prueba con identificadores de otra cuenta y responde 404.
- [ ] **En la base de datos:** con el rol de la aplicación, una consulta sin cuenta fijada no devuelve filas; toda tabla de negocio tiene política RLS.
- [ ] **Agente y búsqueda:** ninguna herramienta ni búsqueda devuelve datos de otra cuenta.
- [ ] **Worker:** cada tarea corre en el contexto de su cuenta.

**Seudonimización**

- [ ] **Captura en `LlmPort`:** en toda la suite, lo que llega al modelo no contiene nombres, NIF, direcciones ni datos de contacto de los datos sintéticos.
- [ ] **Fallo cerrado:** si la seudonimización falla, no se envía nada a Claude.
- [ ] **Restitución:** el usuario ve los datos reales, también si un seudónimo llega partido entre dos fragmentos del streaming.
- [ ] **Contenido:** a `LlmPort` nunca llega un PDF, una imagen ni un audio.
- [ ] **Equivalencias:** la tabla de seudónimos no se guarda en logs ni en `agent_runs`.

**Cuentas y pagos**

- [ ] **Registro:** email ya usado, email sin verificar, enlace caducado y contraseña débil.
- [ ] **Sesiones:** cierre remoto de una sesión, caducidad, recuperación de contraseña y TOTP.
- [ ] **Pago:** el acceso solo se abre con el webhook de la pasarela, nunca por volver a la URL de éxito.
- [ ] **Webhooks:** firma inválida rechazada; evento duplicado o desordenado sin efectos repetidos.
- [ ] **Impago:** cobro fallido, 14 días de reintentos con la app completa, paso a solo lectura y 90 días en ese estado (RN-12); consultar y exportar siguen funcionando. Baja voluntaria: acceso hasta el fin del periodo pagado.
- [ ] **Cierre de cuenta:** exportación ofrecida y borrado que respeta lo que hay que conservar.

**Superadministración**

- [ ] **Acceso:** un cliente recibe 404 en toda la zona; sin TOTP no se entra.
- [ ] **Modelo:** el cambio afecta a toda la plataforma y queda registrado; un modelo no permitido se rechaza.
- [ ] **Sin datos de negocio:** ninguna ruta de la zona devuelve facturas, clientes ni documentos de una cuenta.

**Consumo de IA**

- [ ] **Límites:** al agotar el límite por cuenta o el tope global, la IA se pausa con aviso y el resto sigue funcionando.
- [ ] **Contabilidad:** `ai_usage` coincide con los tokens que informa la API.

**Móvil y voz**

- [ ] **Sin conexión:** la PWA instalada abre, avisa y no permite ni encola escrituras (RF-MO-03). Con `setOffline` de Playwright sobre la app ya cargada.
- [ ] **Service worker:** no guarda respuestas de la API con datos del usuario; al cerrar sesión no quedan datos en el dispositivo.
- [ ] **Actualización:** una versión nueva se avisa sin perder lo que se está escribiendo.
- [ ] **Voz:** grabación vacía, ruido, audio de 2 minutos, permiso de micrófono denegado y Whisper saturado.
- [ ] **Formatos de audio:** el servidor acepta lo que produce MediaRecorder en Chrome, Edge y Safari (`webm/opus` y `mp4`).
- [ ] **Borrado del audio:** no queda ningún fichero tras transcribir, tampoco si falla.

### Pruebas de frontend

- [ ] **Unitarias:** formateo de moneda y fechas, store del chat, parser de SSE, tarjeta de `PendingAction`.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **E2E** con Playwright contra la app servida con `FakeLlm`, en Chromium, WebKit y emulación de móvil: registrar y pagar, importar y revisar, preguntar, presupuesto por chat, facturar por fases, emitir, rectificar, cobrar.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Micrófono simulado:** E2E con `--use-fake-device-for-media-stream` y `--use-file-for-fake-audio-capture`.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 4 — Calidad de la IA

> Se ejecuta con Claude real (`pytest -m llm`), fuera de CI y con presupuesto aprobado. Resultados en `docs/04-evaluacion-ia.md` con fecha, modelo, `effort`, versión del prompt, dataset y coste. Todo se mide sobre texto seudonimizado, que es lo que Claude recibirá en producción.

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
- [ ] **Voz:** WER anotado sobre las grabaciones de oficio, con vocabulario técnico (diferencial, magnetotérmico, rozas, alicatado, solera).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Robustez a inyección:** batería de 20 PDFs y mensajes maliciosos (instrucciones directas, ocultas en tablas, en otro idioma, en metadatos); ninguna herramienta de escritura invocada fuera de propuesta y ninguna fuga del prompt de sistema.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Regresión de prompts:** cambiar un prompt sin volver a pasar la evaluación hace fallar el check (huella del prompt registrada en el informe).
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Estabilidad:** tres ejecuciones con la misma configuración (`claude-opus-5-5` no admite fijar `temperature`); la variación de métricas es < 2 puntos.
  - 🤖 `ingeniero-ia` · Opus 5.5 → escalado a Fable 5.1 si no se alcanza tras dos iteraciones
- [ ] **Fugas hacia Claude:** en el dataset, 0 NIF, emails, teléfonos, IBAN o nombres de clientes registrados, y ≥ 98 % de los nombres no registrados detectados (RNF-17). Incluye nombres en conceptos de línea, direcciones de obra y mensajes dictados.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Coste por seudonimización:** comparar la precisión de extracción con y sin seudónimos, sobre datos sintéticos, para conocer cuánta calidad se paga por la privacidad.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Coste:** coste medio por consulta, por documento y por cuenta típica al mes, frente al precio de la cuota; aciertos de prompt caching anotados.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Cambio de modelo:** antes de que el superadministrador cambie de modelo en producción, esta fase se repite con el nuevo.
  - 🤖 `ingeniero-ia` · Opus 5.5

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
- [ ] **API de Claude caída, 429, 5xx o saldo agotado:** todo lo que no usa IA funciona y el chat explica qué pasa (RNF-08).
  - 🤖 `ingeniero-ia` · Opus 5.5 + `arquitecto-vue` · Sonnet 5.5
- [ ] **Respuesta inválida del modelo:** JSON roto, herramienta inexistente, parámetros inválidos, `stop_reason` `refusal` o `max_tokens` se gestionan de forma acotada y, si persisten, se informa sin colgar el chat.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Ingesta:** un PDF que falla no bloquea la cola; el motivo se ve en la interfaz.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **SSE:** reconexión del frontend y estado consistente si se corta a mitad de respuesta; una desconexión nunca ejecuta una escritura.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Estados** de vacío, carga y error en todas las vistas, diciendo qué ha pasado y qué hacer.
  - 🤖 `ui-ux` · Sonnet 5.5 (diseño) + `arquitecto-vue` · Sonnet 5.5 (implementación)
- [ ] **Pasarela de pago caída:** quien ya paga sigue usando la app; el alta avisa de que no se puede pagar ahora.
  - 🤖 `backend-fastapi` · Opus 5.5

### Pruebas de caos

- [ ] **Caídas:**
  - API de Claude cortada a mitad de una respuesta;
  - PostgreSQL parado a mitad de una emisión;
  - worker parado con tareas en cola;
  - disco lleno durante una subida;
  - Whisper sin memoria;
  - webhook de la pasarela perdido y reenviado;
  - cierre del navegador con una `PendingAction` abierta.
  - 🤖 `plataforma-entrega` · Opus 5.5 (provoca) + `qa-testing` · Opus 5.5 (verifica)

---

## Fase 6 — Observabilidad y operación

- [ ] **Logs:** JSON con `request_id`, `run_id`, `tenant_id`, `use_case`, duración y resultado; **nunca** NIF, nombres de clientes, importes asociados a personas ni texto de documentos.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Rotación y retención** de logs con límite de tamaño y días.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Trazas del agente** en `agent_runs`: herramientas, parámetros sin datos personales, iteraciones, latencia por paso y modelo usado; purga configurable.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Integridad visible:** `verify-billing-chain` corre de forma periódica por cuenta; si falla, salta una alerta y la interfaz avisa. Se ha provocado al menos una vez a propósito.
  - 🤖 `backend-fastapi` · Opus 5.5 + `arquitecto-vue` · Sonnet 5.5
- [ ] **Health check real:** BD con escritura de prueba, worker vivo y espacio en disco. La API de Claude se informa aparte y no marca el servicio como caído.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Alertas:** caída del servicio, tasa de errores, cola atascada, disco, copia fallida, fallo de seudonimización, envíos a la AEAT fallidos y gasto de IA. Cada una tiene su runbook en `docs/operacion/` y **se ha disparado al menos una vez** a propósito.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Métricas internas no expuestas:** `/metrics` no se alcanza desde internet.
  - 🤖 `plataforma-entrega` · Opus 5.5

---

## Fase 7 — Seguridad y cumplimiento

### Automatizado

- [ ] **Dependencias:** `pip-audit` y `npm audit` sin vulnerabilidades altas ni críticas.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **SAST:** bandit y Semgrep (reglas de Python, FastAPI y TypeScript) sin hallazgos altos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **DAST:** ZAP baseline contra staging, también con sesión iniciada.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Imágenes:** Trivy sin CVE críticos; contenedores sin root.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Secretos:** gitleaks sobre todo el historial, sin secretos en fixtures, artefactos ni logs de CI; los PDFs de `samples/` son sintéticos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Licencias de dependencias y modelos** (spaCy, embeddings, Whisper) compatibles con un servicio comercial; atención a las licencias que afectan al uso por red, como AGPL.
  - 🤖 `plataforma-entrega` · Opus 5.5

### Revisión STRIDE

Todos los de este bloque: 🤖 `seguridad-ia` · Opus 5.5 → corrige: el agente dueño.

- [ ] **Suplantación:** Argon2id, sesiones revocables, límites de intentos, mensajes que no revelan si un email existe y TOTP.
- [ ] **Ataques desde el navegador:** cookies `Secure`, `HttpOnly` y `SameSite`, protección CSRF en mutaciones y sin CORS abierto.
- [ ] **Manipulación:** triggers de inmutabilidad, cadena de `BillingRecord` sobre JSON canónico, `PendingAction` firmada y ligada a su cuenta y usuario, y webhooks con firma verificada.
- [ ] **Repudio:** `audit_events` registra emisiones, rectificaciones, cobros, confirmaciones del agente y cambios del superadministrador.
- [ ] **Divulgación:** logs sin datos personales; errores sin trazas internas; un identificador ajeno responde 404.
- [ ] **Denegación:** límites de peticiones por IP y por cuenta, tamaño y páginas en la subida, iteraciones del agente, timeouts hacia Claude y reparto justo de la cola entre cuentas.
- [ ] **Elevación:** el rol de superadministrador no se obtiene por registro ni por la API; subida de ficheros sin ejecución; nombres de fichero saneados.
- [ ] **Configuración:** HSTS, cabeceras de seguridad, CSP sin `unsafe-inline` ni `unsafe-eval` y compatible con el worker de pdf.js, `Permissions-Policy: microphone=(self)`, documentación de la API desactivada en producción, secretos fuera de imágenes y repo, y PostgreSQL sin exponer.

### PDFs no confiables

Un PDF importado es la principal entrada hostil del producto, y se procesa en tres sitios: en el servidor, en el modelo y en el navegador.

- [ ] **Visor en la pantalla de revisión:** `pdfjs-dist` ≥ 4.2.67 (CVE-2024-4367: un PDF con una fuente manipulada ejecuta JavaScript) y `isEvalSupported: false`; el JavaScript embebido no se ejecuta. Prueba con un PDF malicioso de ejemplo.
  - 🤖 `seguridad-ia` · Opus 5.5 (revisa) + `qa-testing` · Opus 5.5 (prueba) → corrige: `arquitecto-vue`
- [ ] **Lectura en el servidor:** pdfplumber y Tesseract corren en el worker con límites de tiempo y memoria; un PDF hostil no tumba el proceso ni la cola.
  - 🤖 `seguridad-ia` · Opus 5.5 (revisa) → corrige: `ingeniero-ia`
- [ ] **Servido del fichero:** los PDFs se sirven por ID, comprobando la cuenta, con `Content-Type` correcto y `X-Content-Type-Options: nosniff`.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`

### Aislamiento entre cuentas

Es el riesgo principal de pasar a multiusuario: un fallo aquí expone datos fiscales de un autónomo a otro.

- [ ] **Prueba parametrizada sobre `openapi.json`:** cada ruta se llama con recursos de otra cuenta. Una ruta nueva queda cubierta sin escribir otra prueba.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Rol de la aplicación** sin `BYPASSRLS` ni propiedad de las tablas; las migraciones usan otro rol.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`
- [ ] **Cuenta fijada por transacción:** una conexión reutilizada del pool no arrastra la cuenta anterior.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Ficheros y caché:** rutas de ficheros por cuenta, y ninguna caché ni prompt caching mezcla datos de cuentas distintas.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`

### Privacidad ante Claude y Anthropic

- [ ] **Revisión de la seudonimización:** ningún camino llega a Claude sin pasar por ella, incluidos reintentos, errores y resultados de herramientas.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `ingeniero-ia`
- [ ] **Riesgo residual documentado:** qué puede escaparse (un nombre no detectado en texto libre) y con qué frecuencia medida (RNF-17). Los datos seudonimizados siguen siendo datos personales.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **Condiciones de Anthropic** (ADR-029): acuerdo de tratamiento, retención, no entrenamiento y región de inferencia, contrastados con las condiciones vigentes. Sin Files API, que conserva los ficheros aunque haya retención cero.
  - 🤖 `seguridad-ia` · Opus 5.5 + 👤
- [ ] **Clave de la API:** solo en el servidor, con espacio de trabajo y límite de gasto propios en la consola de Anthropic.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Modelos locales:** Whisper, spaCy y embeddings incluidos en la imagen o en un volumen, nunca descargados en ejecución; sin telemetría.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Tráfico saliente:** desde el servidor solo se conecta a Anthropic, Stripe, el proveedor de Verifactu, el proveedor de email y el destino de las copias. Cualquier otra conexión es un hallazgo.
  - 🤖 `plataforma-entrega` · Opus 5.5

### Pagos

- [ ] **Tarjetas:** ningún dato de tarjeta pasa por nuestro servidor; el pago ocurre en la página de la pasarela.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **PayPal:** cobros recurrentes activados y probados en una cuenta real de Stripe en España; el modo de pruebas no cubre todos los casos.
  - 🤖 `backend-fastapi` · Opus 5.5 + 👤
- [ ] **Estado de la suscripción:** solo cambia por webhook verificado; el navegador no puede alterarlo.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`

### OWASP Top 10 (aplicaciones web, edición 2025)

> Cada categoría tiene una prueba automatizada en `backend/tests/security/` (o en Playwright cuando corresponde) con el marcador `@pytest.mark.owasp("A0X")`, además del marcador de requisito. `traceability.py --check` falla si alguna categoría se queda sin prueba.

Revisa: 🤖 `seguridad-ia` · Opus 5.5 → corrige: el agente dueño. Automatiza: 🤖 `qa-testing` · Opus 5.5.

| ✓ | Categoría | Riesgo concreto en Kapataz | Mitigación | Ref. | Prueba automatizada |
|---|---|---|---|---|---|
| [ ] | **A01 · Control de acceso roto** (incluye SSRF) | Una cuenta llega a datos de otra cambiando un identificador; un cliente entra en la zona de superadministración; descarga de documentos manipulando rutas | RLS con rol sin `BYPASSRLS`; un identificador ajeno responde 404; documentos servidos por ID, nunca por ruta; zona de superadministración con rol propio y TOTP; el servidor no hace peticiones a URLs que aporte el usuario | RN-10, RNF-13, ADR-024, ADR-031 | `test_a01_idor_todas_las_rutas`, `test_a01_rls_sin_cuenta_sin_filas`, `test_a01_admin_404_para_clientes`, `test_a01_path_traversal_404` |
| [ ] | **A02 · Configuración de seguridad incorrecta** | Documentación de la API, modo depuración o CORS abierto en producción; PostgreSQL o `/metrics` accesibles desde internet | HSTS, CSP sin `unsafe-inline`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy: microphone=(self)`, `/docs` desactivado en producción, sin CORS; solo Caddy expuesto | RNF-12, ADR-013 | `test_a02_cabeceras_seguridad`, `test_a02_docs_desactivado_en_produccion`, ZAP baseline contra staging, escaneo de puertos del servidor |
| [ ] | **A03 · Fallos en la cadena de suministro de software** | Dependencia comprometida; imagen base alterada; acciones de CI secuestradas | `uv.lock` con hashes y `npm ci`; `pip-audit` y `npm audit`; Trivy; imágenes fijadas por digest; SBOM CycloneDX en cada release; acciones de GitHub fijadas por SHA | ADR-022 | Etapa de seguridad del CI; job `sbom-y-auditoria` |
| [ ] | **A04 · Fallos criptográficos** | Contraseñas débiles de guardar; firma de `PendingAction` falsificable; clave en el repo; copias sin cifrar | Argon2id; HMAC de 256 bits con clave en los secretos del servidor; `hmac.compare_digest`; SHA-256 para la cadena; TLS en todo; copias cifradas; ninguna criptografía casera | ADR-018, ADR-025, RNF-15 | `test_a04_firma_alterada_rechazada`, `test_a04_password_argon2id`, regla Semgrep `comparacion-de-firma-con-==` |
| [ ] | **A05 · Inyección** | SQL construido con cadenas; búsqueda de texto inyectada desde el chat; **fórmulas en la exportación CSV/Excel** (`=HYPERLINK(...)` en el nombre de un cliente); **marcado de ReportLab** inyectado en conceptos (`<link>`, `<img>`); XSS en Vue | Consultas parametrizadas, sin `text()` con f-strings; `websearch_to_tsquery` para la búsqueda; celdas que empiezan por `= + - @ \t \r` se prefijan con `'`; todo texto de usuario se escapa antes de pasar a `Paragraph`; prohibido `v-html` | RF-FA-09, RF-PR-06 | `test_a05_busqueda_sintaxis_maliciosa`, `test_a05_csv_formula_neutralizada`, `test_a05_reportlab_marcado_escapado`, regla ESLint `vue/no-v-html`, regla Semgrep `sqlalchemy-text-fstring` |
| [ ] | **A06 · Diseño inseguro** | El agente puede emitir facturas por su cuenta; una factura se puede editar después de emitida; el acceso se abre sin pago real | Modelo de amenazas antes del código (Bloque 0); `PendingAction` con confirmación humana; inmutabilidad en dominio **y** en BD; rectificativas; estado de suscripción solo por webhook | ADR-012, ADR-016, ADR-018, RN-04, RN-F-02 | Escenarios Gherkin «factura emitida inmutable», «inyección en un PDF» y «acceso tras pagar la cuota» |
| [ ] | **A07 · Fallos de autenticación** | Fuerza bruta, enumeración de emails, sesión robada, enlace de recuperación reutilizable | Límite de intentos con bloqueo creciente, mensajes que no revelan si el email existe, cookies `HttpOnly`, `Secure` y `SameSite`, sesiones revocables con caducidad, enlaces de un solo uso, TOTP, sesión renovada tras iniciar sesión | RF-AC, ADR-025 | `test_a07_bloqueo_creciente`, `test_a07_sin_enumeracion`, `test_a07_cookie_flags`, `test_a07_enlace_un_solo_uso`, `test_a07_sesion_revocada` |
| [ ] | **A08 · Fallos de integridad de software y datos** | Cadena de facturación alterada; webhook falsificado que activa una suscripción; despliegue sustituido; deserialización insegura | `verify-billing-chain` periódico; firma de webhooks verificada y eventos sin repetición; imágenes firmadas o fijadas por digest; prohibidos `pickle`, `yaml.load` y `eval` | RN-F-07, ADR-014, ADR-016 | `test_a08_cadena_alterada_detectada`, `test_a08_webhook_sin_firma_rechazado`, `test_a08_webhook_repetido_sin_efecto`, regla Semgrep `no-pickle` |
| [ ] | **A09 · Fallos de registro y alertas** | Un acceso indebido o una alteración de la cadena pasan desapercibidos; los logs filtran NIF o nombres | `audit_events` para toda operación fiscal, confirmación del agente y cambio de superadministración; alertas de inicios de sesión fallidos en masa y de cadena rota; filtro de structlog que enmascara NIF, emails y teléfonos | ADR-015 | `test_a09_aviso_si_cadena_rota`, `test_a09_logs_sin_datos_personales` (recorre los logs de la suite E2E buscando patrones de NIF, email y teléfono) |
| [ ] | **A10 · Manejo incorrecto de condiciones excepcionales** | Una excepción al verificar una firma deja pasar la acción; un fallo de la seudonimización envía datos en claro; un error a mitad de emisión consume número | Fallo cerrado: cualquier excepción en una verificación o en la seudonimización equivale a rechazo; transacción por caso de uso con reversión; `problem+json` sin trazas; schemathesis con datos aleatorios | ADR-009, ADR-030, RN-11, RN-F-01 | `test_a10_verificacion_falla_cerrada`, `test_a10_seudonimizacion_falla_cerrada`, `test_a10_emision_fallida_no_consume_numero`, schemathesis sin respuestas 500 |

### OWASP Top 10 para aplicaciones LLM (edición 2025)

Revisa: 🤖 `seguridad-ia` · Opus 5.5 → corrige: `ingeniero-ia`. Automatiza: 🤖 `qa-testing` · Opus 5.5. Las pruebas que necesitan modelo real llevan además el marcador `llm` y se ejecutan en la Fase 4.

| ✓ | Categoría | Riesgo concreto en Kapataz | Mitigación | Ref. | Prueba automatizada |
|---|---|---|---|---|---|
| [ ] | **LLM01 · Inyección de instrucciones** | Un PDF importado o un concepto escrito por un cliente contiene órdenes para el agente | Contenido recuperado delimitado y marcado como datos; nunca concatenado al prompt de sistema; herramientas de escritura solo como propuesta; lista blanca de herramientas por turno | RN-05, ADR-019 | Batería de 20 casos en `evals/security/` (`pytest -m llm`); `test_llm01_contenido_recuperado_delimitado` (sin modelo, comprueba el prompt construido) |
| [ ] | **LLM02 · Divulgación de información sensible** | Datos de clientes llegan a Anthropic; el agente muestra datos de otra cuenta; las trazas guardan contenido de documentos | Seudonimización antes de Claude; herramientas que devuelven solo los campos necesarios y solo de su cuenta; `agent_runs` sin datos personales | RN-10, RN-11, RNF-17, ADR-030 | `test_llm02_payload_sin_datos_personales`, `test_llm02_herramientas_minimizan_campos`, `test_llm02_agent_runs_sin_datos_personales` |
| [ ] | **LLM03 · Cadena de suministro** | Modelo local sustituido (Whisper, spaCy, embeddings); un cambio de modelo de Claude degrada la calidad sin que se note | Modelos locales fijados por versión y huella; SDK de Anthropic fijado en el lockfile; el modelo de Claude solo lo cambia el superadministrador, con evaluación previa y registro | ADR-005, ADR-022, ADR-031 | `test_llm03_huella_modelos_locales`, `test_llm03_cambio_de_modelo_registrado` |
| [ ] | **LLM04 · Envenenamiento de datos y modelos** | Una factura importada con un precio absurdo contamina el «precio habitual» y los presupuestos futuros; un PDF diseñado para aparecer en todas las búsquedas | Solo cuentan documentos **revisados y aprobados**; mediana sin atípicos (MAD); muestras mínimas; el usuario puede excluir un documento y se recalcula todo; límite de fragmentos por documento; nada cruza entre cuentas | RN-07, RN-08, RN-10, ADR-023 | `test_llm04_atipico_no_altera_mediana`, `test_llm04_documento_en_revision_no_cuenta`, `test_llm04_excluir_documento_recalcula` |
| [ ] | **LLM05 · Manejo inadecuado de la salida** | El texto del modelo se interpreta como HTML; parámetros de herramienta no validados llegan a SQL; enlaces inventados; un seudónimo inventado se restituye mal | Salida renderizada como texto (o Markdown saneado con DOMPurify si se activa); parámetros validados con Pydantic antes de ejecutar; enlaces solo a IDs que devolvió una herramienta; cifras desde el resultado de la herramienta; un seudónimo desconocido no se restituye | RN-02, RF-CO-03 | `test_llm05_parametros_invalidos_rechazados`, `test_llm05_enlace_inexistente_descartado`, `test_llm05_seudonimo_desconocido`, Vitest `chat no renderiza HTML del modelo` |
| [ ] | **LLM06 · Agencia excesiva** | El agente emite, rectifica o registra cobros sin que el usuario lo vea | Ninguna herramienta de escritura ejecuta: todas devuelven `PendingAction` firmada; ninguna herramienta borra; límite de iteraciones; la confirmación solo llega desde la interfaz | RN-04, ADR-018 | `test_llm06_ninguna_herramienta_escribe_directamente` (recorre el registro de herramientas), `test_llm06_pending_action_caducada` |
| [ ] | **LLM07 · Fuga del prompt de sistema** | Alguien obtiene el prompt de sistema | El prompt no contiene secretos, claves ni datos del usuario, así que su fuga tiene impacto bajo; se documenta como riesgo aceptado | ADR-019 | `test_llm07_prompt_sin_secretos` (busca claves, rutas y datos personales en los prompts versionados) |
| [ ] | **LLM08 · Debilidades de vectores y embeddings** | Fragmentos de otra cuenta, o de un documento excluido, aparecen en búsquedas; un cambio de modelo de embeddings mezcla vectores incompatibles; filtros aplicados por el modelo en lugar de por SQL | RLS sobre `chunks`; al excluir o borrar un documento se purgan sus fragmentos en la misma transacción; solo se indexan documentos aprobados; el modelo de embeddings y su dimensión se guardan con el índice; los filtros se aplican en SQL | RN-08, RN-10, ADR-007 | `test_llm08_otra_cuenta_no_aparece`, `test_llm08_documento_excluido_no_aparece`, `test_llm08_cambio_modelo_exige_reindexado`, `test_llm08_filtros_en_sql` |
| [ ] | **LLM09 · Desinformación** | El agente presenta como «precio habitual» una mediana de dos facturas; da por cierta una afirmación fiscal o legal | Cada precio va con número de muestras y rango; con menos de 3 muestras se avisa y no se propone; cifras siempre desde herramientas con fuentes; ante preguntas fiscales o legales remite a la gestoría | RN-02, RN-06, RN-07, RN-09 | `test_llm09_precio_incluye_muestras_y_rango`, `test_llm09_pocas_muestras_avisa`; evaluación `pregunta fiscal remite a gestoría` (`-m llm`) |
| [ ] | **LLM10 · Consumo ilimitado** | Un bucle de herramientas o una cuenta abusiva disparan la factura de Claude; un PDF enorme satura el worker | Límite de iteraciones, tokens de salida y tiempo por turno; límite mensual por cuenta y tope global; alerta de gasto; límites de tamaño y páginas en la subida; duración máxima de audio | ADR-006, ADR-028, RF-UC | `test_llm10_bucle_cortado_por_limite`, `test_llm10_limite_por_cuenta`, `test_llm10_tope_global`, `test_llm10_pdf_excesivo_rechazado`, `test_llm10_audio_excesivo_rechazado` |

### RGPD

Todos los de este bloque: 🤖 `seguridad-ia` · Opus 5.5.

- [ ] **Minimización:** cada campo personal es necesario para presupuestar o facturar.
- [ ] **Roles:** el autónomo es responsable, KodigoLab encargado, y Anthropic, Stripe, el proveedor de Verifactu, el VPS, el email y el destino de las copias son subencargados. Contrato de encargo y lista de subencargados publicados.
- [ ] **Derechos:** exportar y borrar los datos de un cliente concreto, respetando la conservación obligatoria de facturas emitidas.
- [ ] **Conservación:** las facturas emitidas no se purgan; hay plazos para trazas, logs, copias y cuentas cerradas.
- [ ] **Transferencias internacionales:** garantías para los datos que van a Anthropic y a Stripe.
- [ ] **Información al usuario:** política de privacidad, aviso sobre el uso de IA y sobre la seudonimización, y sin fuentes desde CDN ni analítica de terceros.
- [ ] 👤 **Revisión legal** de los textos y de los contratos con un asesor.

### Facturación y Verifactu

- [ ] **Inmutabilidad real**, numeración sin huecos y rectificativas verificadas en código y en BD.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **Conformidad con la normativa vigente:** Real Decreto 1007/2023, Orden HAC/1177/2024 y especificaciones técnicas de la AEAT, contrastadas de nuevo antes de la release.
  - 🤖 `seguridad-ia` · Opus 5.5 + `arquitecto-python` · Opus 5.5
- [ ] **Credenciales del proveedor de Verifactu:** guardadas como secretos, separadas entre staging y producción.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `plataforma-entrega`
- [ ] **Sin doble uso:** ningún camino permite alterar, ocultar o borrar registros de facturación, ni siquiera el superadministrador.
  - 🤖 `seguridad-ia` · Opus 5.5 → corrige: `backend-fastapi`
- [ ] **Suscripción terminada** (RN-12, ADR-016): durante los 90 días de solo lectura se pueden consultar y exportar los datos propios.
  - verifica: 🤖 `seguridad-ia` · Opus 5.5
  - prueba: 🤖 `qa-testing` · Opus 5.5
- [ ] 👤 **Declaración responsable** de la versión que se publica firmada, disponible en la app y conservada junto a las anteriores (RF-VF-06).
- [ ] 👤 **Validación fiscal** con una gestoría o asesor. Fuera del alcance de los agentes.

**Condición de lanzamiento:** ningún cliente real emite facturas hasta cerrar esta sección. Este plan no certifica el cumplimiento fiscal: eso lo confirma el asesor.

---

## Fase 8 — Rendimiento

> El servidor de referencia se fija en el Bloque 1. Anótalo en el informe. Las pruebas de carga simulan la IA con `FakeLlm`, para no gastar dinero, y se lanzan solo contra staging.

- [ ] **Latencia del chat:** primera respuesta visible < 3 s y completa < 15 s en consultas de una herramienta, también con 4G (RNF-04); p50 y p95 sobre el dataset del agente. Registrar el peso del razonamiento de `claude-opus-5-5` y del `effort` elegido.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Ingesta:** < 30 s por PDF de una página (RNF-05), con OCR y seudonimización incluidos; importación de la demo completa medida.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Voz:** audio de 30 s transcrito en < 15 s (RNF-14), también con varias transcripciones en cola.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Reindexado** completo de la demo < 2 min en el servidor de referencia.
  - 🤖 `ingeniero-ia` · Opus 5.5
- [ ] **Carga:** k6 con 100 cuentas activas a la vez sin incumplir RNF-04 (RNF-16); la cola reparte entre cuentas.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Convivencia en el servidor:** Whisper, embeddings, Presidio y PostgreSQL a la vez sin agotar la memoria; límites por contenedor.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **PostgreSQL:** `EXPLAIN` sobre las consultas de las herramientas; ninguna sin índice; RLS no degrada los planes; prueba con 1.000 cuentas sintéticas y 10 años de datos en una de ellas (≈ 5.000 facturas).
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Frontend:** JS inicial ≤ 200 KB gzip, con pdf.js cargado aparte y solo en la pantalla de revisión; LCP ≤ 2 s con 4G en un móvil de gama media; listados de facturas virtualizados a partir de 500 filas.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Resistencia:** 4 h de uso simulado sin fuga de memoria en la API ni en el worker.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 9 — Datos y base de datos

- [ ] **Migraciones:** todas con `downgrade()` probado; ejecución sobre una BD de la versión anterior con datos; compatibles con la versión anterior durante el despliegue.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Invariantes en el esquema:** triggers de inmutabilidad, unicidad de cuenta + serie + año + número, claves foráneas y políticas RLS. Una prueba las recorre tras cada migración.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Transacción de emisión:** el contador se bloquea con `SELECT … FOR UPDATE`; ningún nivel de aislamiento ni pool de conexiones permite un duplicado.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Espacio de demostración:** el borrado solo actúa sobre cuentas de ese tipo y no abre ningún camino sobre facturas reales.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Copias de seguridad:** cifradas, fuera del servidor y en la UE, con archivado de WAL y RPO ≤ 15 min (RNF-15); ficheros de PDFs incluidos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Simulacro de restauración** en un servidor vacío, con RTO ≤ 4 h: facturas, documentos, cadena de registros y siguiente número intactos, en varias cuentas. Se anota el tiempo.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Exportación de cuenta** completa y legible; contiene solo datos de esa cuenta.
  - 🤖 `qa-testing` · Opus 5.5

---

## Fase 10 — Despliegue y entrega

- [ ] **CI por etapas**, falla si algo falla; ningún check se ha omitido por cambios en rutas o en nombres de workflow.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **PRs de bloque:** todos integrados con sus checks requeridos en verde; las excepciones aprobadas están en el registro.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Despliegue:** staging antes que producción, migraciones controladas, health checks reales y parada mínima, con las sesiones y las tareas en curso conservadas.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Vuelta atrás** probada: un despliegue fallido deja la versión anterior funcionando.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Servidor:** cortafuegos, acceso SSH por clave, actualizaciones de seguridad y solo los puertos 80 y 443 abiertos.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **TLS:** renovación automática probada; calificación A o superior en un análisis externo.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Email:** SPF, DKIM y DMARC configurados; los emails de verificación y recuperación no caen en spam.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Stripe y Verifactu en producción:** claves y webhooks separados de los de staging; el entorno de pruebas de la AEAT nunca se usa con datos reales.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Artefacto de release:** sin datos de usuario, secretos ni PDFs reales; SBOM incluido.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] 👤 **Alta real de principio a fin** con un pago real con tarjeta y otro con PayPal, en un móvil y por alguien no técnico. Anota lo que tarda.

---

## Fase 11 — Documentación

- [ ] **Documentación de usuario:** primeros pasos, instalar la PWA, uso, suscripción y baja, y «qué hacer si…» para cada fallo previsible.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **Documentación de operación:** despliegue, vuelta atrás, restauración y un runbook por alerta en `docs/operacion/`, ejecutados tal cual.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **README y caso de estudio:** cifras sacadas de `docs/04-evaluacion-ia.md`, sin datos inventados.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **Limitaciones documentadas:** qué funciones dependen de Claude y qué recibe Anthropic.
  - 🤖 `documentacion-portafolio` · Sonnet 5.5
- [ ] **`HANDOFF.md` al día** y coherente con el estado real de la release; Engram no contiene datos de clientes ni secretos.
  - 🤖 hilo principal · Sonnet 5.5
- [ ] **ADR al día:** ninguna decisión estructural sin ADR y ninguno en «Propuesto».
  - 🤖 `arquitecto-python` · Opus 5.5
- [ ] **Contrato:** `openapi.json` coincide exactamente con la implementación.
  - 🤖 `backend-fastapi` · Opus 5.5
- [ ] **Modelo de amenazas** actualizado con lo encontrado en la Fase 7.
  - 🤖 `seguridad-ia` · Opus 5.5

---

## Fase 12 — Accesibilidad, móvil y UX

- [ ] **Contraste** WCAG 2.2 AA medido en todas las parejas de tokens, con prueba automatizada.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] **axe:** `@axe-core/playwright` sin violaciones críticas ni graves en todas las vistas.
  - 🤖 `qa-testing` · Opus 5.5
- [ ] **Teclado:** flujo completo (preguntar, revisar extracción, crear presupuesto, emitir) sin ratón; foco visible.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Móvil:** todas las vistas usables a 360 px, incluida la revisión de PDF; objetivos táctiles ≥ 44 px; botón de micrófono alcanzable con el pulgar.
  - 🤖 `arquitecto-vue` · Sonnet 5.5 + `ui-ux` · Sonnet 5.5
- [ ] **PWA:** instalación y uso en Android con Chrome y en iPhone con Safari, con el micrófono funcionando en la app instalada.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Lectores de pantalla:** regiones vivas en el chat y en el progreso de ingesta; tablas de importes con encabezados asociados.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **i18n:** ningún literal en componentes; fechas e importes en formato español.
  - 🤖 `arquitecto-vue` · Sonnet 5.5
- [ ] **Estados del micrófono:** inactivo, escuchando, transcribiendo y error se distinguen sin depender solo del color.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] **Coherencia visual** entre pantallas y PDFs, con importes idénticos en ambos; `prefers-reduced-motion` respetado; modo oscuro completo.
  - 🤖 `ui-ux` · Sonnet 5.5
- [ ] 👤 **Prueba en móviles reales:** un Android de gama media y un iPhone, con 4G, sol directo y ruido de fondo.
- [ ] 👤 **Prueba con un usuario de oficio real:** que se registre, pague, cree un presupuesto por voz y lo convierta en factura sin ayuda. Anota dónde duda.

---

## Fase 13 — Revisión final

- [ ] **Revisión del diff completo** de la release contra la Definición de Terminado.
  - 🤖 `revisor-codigo` · Opus 5.5 → corrige: el agente dueño
- [ ] **Pasada final de seguridad y cumplimiento** sobre lo corregido.
  - 🤖 `seguridad-ia` · Opus 5.5
- [ ] **Re-revisión** de cada hallazgo corregido por el mismo agente que lo detectó; cada corrección lleva su prueba de regresión.
- [ ] **Publicar la 1.0.0:** `VERSION`, `CHANGELOG.md`, etiqueta `v1.0.0`, imagen, release en GitHub, declaración responsable e instrucciones de vuelta atrás comprobados.
  - 🤖 `plataforma-entrega` · Opus 5.5
- [ ] **Activar el control de versión en CI:** desde aquí, un PR que cambia la app sin subir la versión ni actualizar el changelog falla.
  - 🤖 `plataforma-entrega` · Opus 5.5

---

## ✅ Criterios de salida

- [ ] Decisiones de «Antes de empezar» cerradas.
- [ ] Todos los PR de bloque integrados con CI, seguridad y revisión en verde.
- [ ] La candidata verificada es exactamente la que se publica como 1.0.0.
- [ ] `traceability.py --check` en verde: ningún requisito ni categoría OWASP sin prueba.
- [ ] Calidad de backend, frontend y scripts en verde; build e imágenes correctos.
- [ ] Umbrales: cobertura (90 / 80 / 70 %), mutación ≥ 80 % en `domain/billing`, suite unitaria < 10 s.
- [ ] Métricas de IA cumplidas: extracción ≥ 95 %, herramienta ≥ 90 %, parámetros ≥ 90 %, recall@5 ≥ 0,85, **0 cifras no procedentes de herramientas**, 0 fuentes inventadas y 0 escrituras sin confirmación en la batería de inyección.
- [ ] **Privacidad:** RNF-17 cumplido; a Claude nunca llega un PDF, una imagen ni un audio.
- [ ] **Aislamiento:** ningún acceso entre cuentas en toda la API, el agente, la búsqueda y el worker.
- [ ] Objetivos de rendimiento RNF-04, RNF-05, RNF-14 y RNF-16 medidos y cumplidos.
- [ ] Coste de IA por cuenta medido y compatible con la cuota.
- [ ] **0 hallazgos 🔴 CRÍTICO ni 🟠 ALTO** de `seguridad-ia`.
- [ ] **0 hallazgos 🔴 BLOQUEANTE** de `revisor-codigo`.
- [ ] Numeración concurrente, inmutabilidad y cadena de registros verificadas.
- [ ] Pagos con tarjeta y PayPal, impago y paso a solo lectura verificados.
- [ ] Restauración probada con RPO y RTO cumplidos; despliegue con vuelta atrás probado.
- [ ] 👤 Prueba en móviles reales superada.
- [ ] 👤 Prueba con usuario de oficio realizada y hallazgos registrados.
- [ ] 👤 Revisión legal de privacidad, contratos y condiciones.
- [ ] Verifactu verificado: registros, huella, QR y envío aceptado en el entorno de pruebas de la AEAT; autorización de clientes resuelta.
- [ ] 👤 Declaración responsable firmada y validación fiscal de un asesor antes de que un cliente real emita facturas.

---

## Registro de hallazgos

| # | Fase / PR | Descripción y evidencia | Severidad | Detecta | Corrige | Estado |
|---|---|---|---|---|---|---|
| 1 |  |  |  | `agente` | `agente` | Abierto / Corregido / Re-revisado |
