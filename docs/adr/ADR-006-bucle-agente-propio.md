# ADR-006 — Bucle de agente propio sin frameworks

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-CO-01, RF-CO-02, RF-CO-05, RF-CO-07, RF-PR-03, RN-02, RN-04, RN-05, RN-11, RNF-04, RNF-07, RNF-08

## Contexto

El agente responde preguntas y prepara presupuestos, facturas, cobros y rectificativas. Cada paso del bucle tiene una regla que no se puede romper:

- Ninguna escritura se ejecuta sin confirmación del usuario en la interfaz (RN-04, RF-PR-03).
- El contenido de un documento es dato, nunca instrucción (RN-05).
- Toda cifra procede de una herramienta (RF-CO-02, RN-02).
- Todo lo que va a Claude pasa por la seudonimización, y los datos reales se restituyen al responder (RN-11).
- El usuario puede ver qué herramientas se usaron y con qué parámetros (RF-CO-07).
- El bucle tiene un máximo de iteraciones para acotar el coste (ADR-028) y emite por SSE (RNF-04).

Necesitamos controlar exactamente dónde se ejecuta cada herramienta y qué entra y sale del modelo.

## Opciones consideradas

1. **Bucle propio sobre el tool use de la Messages API**, detrás de `LlmPort`.
   - Ventajas: control total del punto en que una herramienta de escritura se convierte en propuesta; cada mensaje pasa por la seudonimización; trazas a medida; pocas dependencias; se prueba con `FakeLlm`.
   - Inconvenientes: hay que escribir el bucle, los reintentos, el límite de iteraciones y el streaming.
2. **Framework de agentes (LangChain o similar)**
   - Ventajas: abstracciones hechas (memoria, agentes, varios proveedores).
   - Inconvenientes: muchas dependencias que cambian a menudo (ADR-022); la abstracción esconde justo el punto donde se ejecutan las herramientas, que es donde va la confirmación; más difícil garantizar que todo pasa por la seudonimización.
3. **Ejecutor automático de herramientas del SDK de Anthropic**
   - Ventajas: menos código propio.
   - Inconvenientes: ejecuta las herramientas dentro del SDK, así que la seudonimización de resultados, las trazas y las propuestas necesitan ganchos; ata la capa de aplicación al SDK, en contra de ADR-001.

## Decisión

Opción 1. El orquestador vive en `application/agent` y solo habla con `LlmPort`. Sigue el flujo de §4.6:

1. Comprueba el límite de uso de la cuenta.
2. Construye el contexto: prompt de sistema versionado en ficheros, herramientas disponibles, últimos turnos y fragmentos recuperados delimitados como datos. Todo pasa por `PseudonymizerPort`.
3. Claude responde con texto o con llamadas a herramientas. Sistema y herramientas forman un prefijo estable para el prompt caching.
4. Cada llamada se valida con el esquema Pydantic de su herramienta, definido en `application/agent`; ante una entrada inválida hay un reintento acotado. El catálogo de herramientas (nombre y si son de lectura o de escritura) y las políticas de confirmación viven en `domain/assistant`, que es Python puro. Las herramientas de lectura se ejecutan como casos de uso que devuelven DTO. Las de escritura solo producen una `PendingAction` (ADR-018).
5. Los resultados vuelven al modelo, con un máximo de iteraciones configurable (6 por defecto).
6. La respuesta se emite por SSE. El servidor restituye los datos reales y las cifras se renderizan desde el resultado de la herramienta.

Cada ejecución se guarda en `agent_runs` y `agent_steps` (herramienta, parámetros y duración), sin contenido de documentos. La lista blanca de herramientas por turno la define ADR-019.

## Consecuencias

- **Positivas**
  - Las reglas RN-04, RN-05 y RN-11 se aplican en código nuestro, visible y probado.
  - Cambiar de proveedor de LLM solo afecta al adaptador.
- **Negativas y mitigación**
  - Más código propio → bucle pequeño, con pruebas sobre `FakeLlm` para cada rama: texto, herramienta, entrada inválida, máximo de iteraciones y error de la API.
  - Funciones que daría un framework (memoria larga, varios agentes) → no hacen falta en la v1.
- **Qué haría reconsiderarla**
  - Que el bucle crezca hasta duplicar lo que ofrece un framework maduro que permita controlar la ejecución de herramientas y la seudonimización.
  - Que la v1 necesite varios agentes coordinados.

## Verificación

- **import-linter:** `kapataz.application` no importa `anthropic` (ADR-001); el bucle solo conoce `LlmPort`.
- **Revisión de PR:** añadir un framework de agentes a `pyproject.toml` exige sustituir este ADR.
- Pruebas en `tests/unit/agent/` con `FakeLlm`:
  - `test_herramienta_de_escritura_solo_crea_pending_action`, `@pytest.mark.req("RN-04")`.
  - `test_bucle_se_detiene_en_el_maximo_de_iteraciones`, `@pytest.mark.req("RF-CO-01")`.
  - `test_parametros_invalidos_se_rechazan_con_reintento_acotado`, `@pytest.mark.req("RF-CO-01")`.
  - `test_traza_guarda_herramienta_y_parametros_sin_contenido`, `@pytest.mark.req("RF-CO-07")`.
  - `test_cifra_de_la_respuesta_sale_de_la_herramienta`, `@pytest.mark.req("RF-CO-02")`.
- **Escenario «Inyección de instrucciones en un PDF»:** no se invoca ninguna herramienta de escritura. `@pytest.mark.req("RN-05")`.
- **Evaluación** de selección de herramienta (RNF-07) con `pytest -m llm`, fuera de CI.
