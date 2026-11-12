# ADR-008 — LLM falso determinista en CI; evaluaciones con Claude real fuera de CI

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RNF-06, RNF-07, RNF-08, RNF-16, RNF-17, RN-04, RN-05

## Contexto

El comportamiento del agente y de la extracción depende de una API de pago y no determinista. CI se ejecuta en cada PR y sus comprobaciones son requisito para integrar (§7). La regla de calidad es cero pruebas intermitentes.

Al mismo tiempo, la calidad real del modelo hay que medirla: precisión de extracción (RNF-06), selección de herramienta (RNF-07) y fugas de datos hacia Claude (RNF-17). Y la prueba de carga (RNF-16) se hace con la IA simulada.

La clave de la API solo debe existir en el servidor.

## Opciones consideradas

1. **`FakeLlm` determinista en CI y evaluaciones con Claude real fuera de CI** (`pytest -m llm`, manual y con presupuesto aprobado).
   - Ventajas: CI reproducible, sin clave y sin coste; las pruebas fijan exactamente qué responde el modelo, incluidos errores y casos maliciosos.
   - Inconvenientes: CI no detecta una regresión de calidad del modelo; hay que acordarse de evaluar.
2. **Claude real en CI**
   - Ventajas: detecta regresiones del modelo en cada PR.
   - Inconvenientes: coste en cada PR; la clave pasa a ser un secreto de CI; respuestas no deterministas que vuelven intermitentes las pruebas.
3. **Grabar y reproducir respuestas reales**
   - Ventajas: respuestas realistas sin coste en cada ejecución.
   - Inconvenientes: las grabaciones caducan con cada cambio de prompt o de herramienta; regenerarlas exige llamadas reales; pruebas frágiles que no prueban la lógica propia mejor que un falso.

## Decisión

Opción 1.

- **`FakeLlm`** implementa `LlmPort` y devuelve, según el guion de cada prueba, texto, llamadas a herramientas o errores (429, 5xx, `refusal`, `max_tokens`).
- **Gemelos deterministas** de los demás puertos externos: `FakeEmbeddings`, `FakePseudonymizer` para las unitarias, `FakeTranscription`, `FakePdfText`, `FakeOcr`, `FakePdfRender`, `FakeSubscriptions`, `FakeEmail` y `FrozenClock`.
- La seudonimización real (`PresidioPseudonymizer`) corre en nuestro servidor y sin coste, así que las pruebas de fuga la usan en CI con `FakeLlm` capturando lo que llega a `LlmPort`.
- **Marcadores de pytest:** `req`, `llm` y `slow`. CI ejecuta `pytest -m "not llm"`.
- **Evaluaciones:** `pytest -m llm` solo a mano. Antes de cada ejecución se estima el coste y se pide aprobación. Los resultados van a `docs/04-evaluacion-ia.md` con modelo, `effort`, métricas, coste y fecha.
- E2E con Playwright y prueba de carga con k6 usan `FakeLlm`.

## Consecuencias

- **Positivas**
  - CI rápida, gratuita y reproducible.
  - Los casos difíciles (inyección, caída de la API, respuestas inválidas) se prueban siempre igual.
  - La clave de la API no sale del servidor.
- **Negativas y mitigación**
  - Una regresión del modelo no se ve en CI → evaluaciones con Claude real en los bloques 4 y 6 y en la fase 4 de la Parte II.
  - El falso puede divergir del comportamiento real → su contrato es el mismo `LlmPort`, y las pruebas de `ClaudeLlm` contra la API real llevan el marcador `llm`.
- **Qué haría reconsiderarla**
  - Que las evaluaciones manuales dejen pasar regresiones que CI habría detectado.
  - Una forma de ejecutar el modelo en CI determinista y sin coste.

## Verificación

- **CI:** el workflow ejecuta `uv run pytest -m "not llm"` y no define la clave de la API de Claude. Si una prueba intenta usar `ClaudeLlm`, falla por falta de clave en lugar de pasar en silencio.
- **pytest** con `--strict-markers`: un marcador mal escrito hace fallar la ejecución.
- `tests/security/test_fuga_hacia_llm.py`: con `PresidioPseudonymizer` y `FakeLlm` capturando, lo enviado no contiene NIF, emails, teléfonos, IBAN ni nombres de clientes registrados. `@pytest.mark.req("RNF-17")`.
- **Escenario «Claude no responde»** con `FakeLlm` que devuelve error. `@pytest.mark.req("RNF-08")`.
- **Escenario «Inyección de instrucciones en un PDF»** con `FakeLlm` que intenta llamar a una herramienta de escritura. `@pytest.mark.req("RN-05")`.
- **Informes** de `pytest -m llm` en `docs/04-evaluacion-ia.md`, citados en la descripción del PR del bloque.
