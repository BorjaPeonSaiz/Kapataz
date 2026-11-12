# ADR-005 — Claude como LLM

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-SA-02, RF-SA-06, RF-UC-01, RF-UC-02, RN-02, RN-11, RNF-01, RNF-04, RNF-06, RNF-07, RNF-08
- **Se cierra en:** Bloque 6

## Contexto

Kapataz usa un LLM en tres rutas: el chat con herramientas, la clasificación de documentos y la extracción estructurada. Las exigencias son altas:

- Extracción con precisión ≥ 95 % en campos críticos (RNF-06) y selección de herramienta ≥ 90 % (RNF-07).
- Primera respuesta visible en menos de 3 s (RNF-04).
- El coste de la IA va incluido en la cuota, con un límite por cuenta (RF-UC-01, ADR-028).
- Al modelo solo llega texto seudonimizado (RN-11, ADR-030); el tratamiento con Anthropic se regula en ADR-029.
- Si la API no responde, lo que no usa IA sigue funcionando (RNF-08).

El modelo no calcula importes (RN-02), no transcribe audio (ADR-011) y no genera embeddings (ADR-007).

## Opciones consideradas

1. **API de Claude con clave de KodigoLab y un solo modelo para toda la plataforma** (`claude-opus-5-5`), que solo cambia el superadministrador, con `effort` por ruta.
   - Ventajas: calidad en tool use y extracción; una sola configuración que evaluar; coste controlado desde un sitio; la clave solo está en el servidor.
   - Inconvenientes: coste por consulta más alto que con un modelo menor; dependencia de un proveedor que almacena los datos en Estados Unidos (ADR-029).
2. **Un modelo distinto por ruta** (por ejemplo, uno menor para clasificar).
   - Ventajas: menos coste en las rutas sencillas.
   - Inconvenientes: más combinaciones que evaluar y mantener; el `effort` por ruta ya da un margen de ajuste del coste con un solo modelo.
3. **Cada cliente elige su modelo o aporta su propia clave.**
   - Ventajas: el coste pasa al cliente.
   - Inconvenientes: contradice RF-SA-02 y la regla de que la clave solo existe en el servidor; cada combinación necesitaría su evaluación; complica el soporte.
4. **Otro proveedor o un modelo abierto en nuestro servidor.**
   - Ventajas: los datos podrían quedarse en la UE.
   - Inconvenientes: el plan elige Claude por su calidad en tool use y extracción; un modelo capaz en local exige un hardware que el servidor de ADR-014 no prevé. `LlmPort` deja la puerta abierta.

## Decisión (propuesta)

Opción 1.

- Todas las cuentas y todas las rutas usan `claude-opus-5-5`. Los clientes no tienen ningún ajuste de modelo.
- El modelo y el `effort` por ruta se leen de `platform_settings`; nunca se fijan en el código. Solo el superadministrador los cambia, para toda la plataforma (RF-SA-02), y el cambio queda registrado (RF-SA-06).
- Se usa el SDK oficial `anthropic`, solo dentro del adaptador `ClaudeLlm`. La clave solo existe en el servidor.
- Según el plan, este modelo no admite `temperature` ni forzar una herramienta con `tool_choice`: se usa `auto`, `strict: true` en las herramientas y un `effort` explícito. Antes de usar un parámetro se comprueba en la documentación oficial vigente.
- Se comprueba `stop_reason` antes de leer la respuesta y se gestionan `refusal`, `max_tokens` y los errores 429 y 5xx.
- El prompt de sistema y las herramientas forman un prefijo estable para el prompt caching.

## Pendiente para cerrar

Se cierra en el Bloque 6 con datos de `evals/`:

- **`effort` de cada ruta** (chat, clasificación y extracción). Datos: precisión de herramienta, exactitud de parámetros, latencia y coste por pregunta sobre el dataset del agente (80–120 preguntas), con el coste de la evaluación aprobado antes.
- **Cumplimiento de umbrales** con el `effort` elegido: RNF-04 y RNF-07 en el Bloque 6; RNF-06, medido ya en el Bloque 4 con un `effort` provisional para la extracción.
- **Coste medio por consulta**, que alimenta los límites de ADR-028.
- **Dependencia externa:** las condiciones de ADR-029 (retención, aviso de subencargados, evaluación de impacto de la transferencia) deben estar resueltas antes de usar datos reales.

## Consecuencias

- **Positivas**
  - Una sola configuración que evaluar, documentar y vigilar.
  - El superadministrador cambia de modelo sin desplegar.
- **Negativas y mitigación**
  - Coste → límites por cuenta y tope global (ADR-028), prompt caching y `effort` por ruta.
  - Latencia de un modelo grande → streaming por SSE y `effort` ajustado por ruta.
  - Caídas de la API → el resto de la app no depende de ella (RNF-08).
  - Datos fuera de la UE → seudonimización (ADR-030) y condiciones de ADR-029.
- **Qué haría reconsiderarla**
  - Que la evaluación no alcance RNF-06 o RNF-07 tras dos iteraciones.
  - Que el coste por consulta no quepa en la cuota.
  - Un cambio en las condiciones de tratamiento de Anthropic o la retirada del modelo.
  - Que se quiera pasar a Claude Fable o Claude Mythos: son «Covered Models», exigen 30 días de retención y no admiten retención cero salvo autorización expresa de Anthropic (ADR-029). `claude-opus-5-5` sí la admite.

## Verificación

- **import-linter:** contrato `forbidden` por el que solo `kapataz.infrastructure.llm` importa `anthropic`.
- **Escenario «Zona de superadministración»:** un cliente recibe 404 y no existe ningún ajuste de modelo en su cuenta. `@pytest.mark.req("RF-SA-02")`.
- **Escenario «Claude no responde»** con `FakeLlm` configurado para fallar: listados y emisión funcionan y el chat lo explica. `@pytest.mark.req("RNF-08")`.
- **Prueba de configuración:** `ClaudeLlm` usa el modelo de `platform_settings` y un cambio queda en el registro de cambios. `@pytest.mark.req("RF-SA-06")`.
- **Evaluaciones** con `pytest -m llm`, fuera de CI (ADR-008), con informe en `docs/04-evaluacion-ia.md`: modelo, `effort`, métricas, coste y fecha.
- **CI:** gitleaks comprueba que ninguna clave de API entra en el repositorio.
