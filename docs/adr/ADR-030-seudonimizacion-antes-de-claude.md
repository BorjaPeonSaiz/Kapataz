# ADR-030 — Seudonimización antes de Claude

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-11, RNF-01, RNF-17, RNF-06, RF-AC-05, RF-VO-03, RF-IN-03
- **Se cierra en:** Bloque 6

## Contexto

Kapataz envía texto a la API de Claude para clasificar y extraer documentos y para responder en el chat. Ese texto contiene nombres, NIF, direcciones, emails y teléfonos de los clientes y proveedores del autónomo, y sus propios datos. Anthropic almacena los datos en Estados Unidos y no hay tratamiento solo en la UE (ADR-029).

RN-11 exige que el servidor sustituya esos datos por seudónimos antes de enviar nada, que a Claude nunca llegue un PDF, una imagen ni un audio, y que si la seudonimización falla la petición no se envíe. RNF-17 fija el objetivo: 0 NIF, emails, teléfonos, IBAN o nombres de clientes registrados en lo enviado, y al menos el 98 % de los nombres no registrados detectados.

Los datos seudonimizados siguen siendo datos personales (considerando 26 del RGPD): esto reduce el riesgo, no cambia los papeles de RGPD (ADR-029). Además, la extracción tiene que seguir alcanzando RNF-06 sobre texto seudonimizado.

## Opciones consideradas

1. **Enviar el texto en claro y confiar en el contrato con Anthropic.**
   - Ventajas: máxima calidad y ninguna pieza extra.
   - Inconvenientes: incumple RN-11 y RNF-01; todo dato de cliente sale de la UE.
2. **Anonimización irreversible.**
   - Ventajas: menos riesgo si el texto se filtra.
   - Inconvenientes: el usuario necesita ver «Marta López García» en la respuesta; sin restitución, el chat y la extracción no sirven.
3. **Solo patrones** (NIF, IBAN, email, teléfono).
   - Ventajas: determinista y rápido.
   - Inconvenientes: no detecta nombres ni direcciones; incumple RNF-17.
4. **Diccionario de la cuenta, patrones y Presidio con spaCy `es_core_news_md`, con restitución en el servidor.**
   - Ventajas: los datos conocidos se sustituyen siempre; los patrones cubren identificadores; Presidio detecta nombres y direcciones no registrados; todo corre en nuestro servidor.
   - Inconvenientes: el reconocimiento de nombres no es perfecto; cuesta algo de calidad en la extracción.
5. **Modelo de lenguaje propio en nuestro servidor, sin enviar nada fuera.**
   - Ventajas: ningún dato sale.
   - Inconvenientes: un servidor con GPU fuera del presupuesto de un VPS; calidad inferior en tool use y extracción (ADR-005).

## Decisión

Propuesta: opción 4.

- **Tres capas** en `PseudonymizerPort` (`PresidioPseudonymizer`):
  1. diccionario de la cuenta: clientes, proveedores y datos del profesional registrados;
  2. patrones: NIF, IBAN, email y teléfono;
  3. Presidio con spaCy `es_core_news_md` para nombres y direcciones no registrados.
- **Puerta única:** `LlmPort` solo acepta `SanitizedPrompt`. Solo `PseudonymizerPort` puede construirlo. No hay otro camino hacia el SDK de Anthropic.
- **Fallo cerrado:** cualquier error de la seudonimización impide el envío.
- **Restitución en el servidor:** Claude ve `[CLIENTE_1]`; la tabla de equivalencias (`Alias`) se queda en el servidor y se restituye antes de responder, también durante el streaming y cuando un seudónimo llega partido entre dos fragmentos. Un seudónimo desconocido no se restituye.
- **Todo lo que va a Claude pasa por aquí:** mensajes, transcripciones, fragmentos recuperados, resultados de herramientas, reintentos y errores.
- **Nunca se envía** un PDF, una imagen ni un audio: el texto se obtiene en nuestro servidor (ADR-010, ADR-011).
- La tabla de equivalencias no se guarda en logs ni en `agent_runs`.
- El usuario sabe, antes de usar la IA, que Anthropic recibe solo texto seudonimizado (RNF-01).

## Consecuencias

- **Positivas:**
  - Los datos registrados nunca salen en claro.
  - Una sola puerta hacia Claude, fácil de revisar y de probar.
  - El riesgo residual se mide, no se supone.
- **Negativas y mitigación:**
  - Un nombre no registrado en texto libre puede escaparse. Se mide con RNF-17 y se documenta como riesgo residual.
  - La extracción puede perder precisión. Se mide comparando con y sin seudónimos sobre datos sintéticos (Fase 4).
  - Presidio y spaCy añaden latencia y memoria. Se miden contra RNF-04 y RNF-05.
- **Qué haría reconsiderarla:** que RNF-17 o RNF-06 no se alcancen con esta combinación, o que Anthropic ofrezca tratamiento solo en la UE con garantías que cambien el análisis de ADR-029.

## Pendiente para cerrar

Se mide por primera vez en el Bloque 4, con la evaluación de extracción con Claude real sobre los datos sintéticos del Bloque 3. Se cierra en el Bloque 6, al cubrir también el chat:

- **RNF-17 medido:** fugas de NIF, emails, teléfonos, IBAN y nombres registrados, y porcentaje de nombres no registrados detectados, incluidos nombres en conceptos de línea, direcciones de obra y mensajes dictados.
- **RNF-06 medido** sobre texto seudonimizado y diferencia frente al texto en claro (coste de la privacidad).
- **Modelo de spaCy:** si `es_core_news_md` basta o hace falta otro.
- **Alcance de los seudónimos:** si `[CLIENTE_1]` es estable por conversación, por documento o por cuenta, y cómo afecta al prompt caching sin mezclar cuentas.
- **Seudonimización del chat** (Bloque 6): mensajes, resultados de herramientas y fragmentos recuperados, con los nombres reales restituidos también durante el streaming. RNF-17 se vuelve a medir con lo que capturan las evaluaciones del agente.
- ~~Qué datos del profesional se seudonimizan.~~ **Resuelto:** RNF-01 y RN-11 incluyen los nombres, NIF, direcciones y datos de contacto del propio profesional.
- ~~Si el cierre en el Bloque 4 cubre el chat.~~ **Resuelto:** el Bloque 4 hace la primera medición y el ADR se cierra en el Bloque 6.

## Verificación

- Escenario «Claude no ve los datos del cliente» (`@pytest.mark.req("RN-11")`).
- `test_llm02_payload_sin_datos_personales`: captura en `LlmPort` de toda la suite; ningún dato personal de los datos sintéticos (`req("RNF-17")`).
- `test_a10_seudonimizacion_falla_cerrada` (`req("RN-11")`, `owasp("A10")`).
- `test_llm05_seudonimo_desconocido` y prueba de restitución con el seudónimo partido entre dos fragmentos.
- Prueba de que a `LlmPort` nunca llega un PDF, una imagen ni un audio.
- Prueba de que la tabla de equivalencias no aparece en logs ni en `agent_runs`.
- Regla de import-linter: solo `infrastructure/llm` importa el SDK `anthropic`; `domain` y `application` no lo importan.
- Evaluación de fugas de la Fase 4 (`pytest -m llm`, fuera de CI).
