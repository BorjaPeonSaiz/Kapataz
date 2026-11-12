# ADR-018 — Confirmación humana obligatoria para escrituras del agente

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-04, RN-05, RF-PR-03, RF-FA-01, RF-FA-08, RN-F-10, RN-F-11
- **Se cierra en:** Bloque 6

## Contexto

El agente tiene herramientas que crean o cambian datos con efecto fiscal: `proponer_presupuesto`, `proponer_factura`, `proponer_cobro` y `proponer_rectificativa` (§4.6). Un error del modelo, una petición mal entendida o una instrucción escondida en un PDF (RN-05, ADR-019) no puede acabar en una factura emitida o en un cobro registrado.

RN-04 exige que ninguna escritura se ejecute desde el agente sin confirmación explícita del usuario en la interfaz. RF-PR-03 añade que el agente siempre crea un borrador y lo muestra. Una factura emitida no se puede deshacer, solo rectificar (RN-F-02), así que «ejecutar y deshacer después» no sirve.

La confirmación tiene que resistir manipulación: una propuesta alterada en el navegador, reutilizada desde otra cuenta, confirmada dos veces o confirmada días después.

## Opciones consideradas

1. **El agente ejecuta y el usuario deshace si no está de acuerdo.**
   - Ventajas: flujo más corto en el chat.
   - Inconvenientes: incumple RN-04. Una emisión no se deshace, consume número y genera `BillingRecord`.
2. **Confirmación conversacional: el usuario escribe «sí» y el modelo llama a la herramienta de escritura.**
   - Ventajas: natural en un chat; no necesita componentes nuevos.
   - Inconvenientes: quien decide sigue siendo el modelo. Un PDF con instrucciones o una respuesta ambigua bastan para escribir. No hay prueba de qué vio el usuario.
3. **Propuesta guardada en el servidor y confirmada por identificador, sin firma.**
   - Ventajas: sencilla; el servidor conoce el contenido exacto.
   - Inconvenientes: la integridad depende de que nadie altere la fila ni el identificador; sin ligar a cuenta y usuario es vulnerable a reutilización.
4. **`PendingAction` firmada, con caducidad, ligada a cuenta y usuario, que solo confirma la interfaz.**
   - Ventajas: el modelo nunca escribe; la propuesta no se puede alterar sin que falle la firma; caduca; se ejecuta una sola vez.
   - Inconvenientes: más piezas (clave, endpoint, tarjeta en la UI) y un paso más para el usuario.

## Decisión

Se elige la opción 4.

- Las herramientas de escritura no ejecutan nada. Validan sus parámetros con su esquema Pydantic, definido en `application/agent`, y devuelven una `PendingAction` con la operación exacta, el `tenant_id`, el `user_id` y la fecha de caducidad (leída del `Clock`).
- La `PendingAction` va firmada con HMAC de 256 bits. La clave está en los secretos del servidor. La firma se compara con `hmac.compare_digest`.
- La interfaz muestra la propuesta con los botones Confirmar y Descartar. Solo un endpoint de la API, llamado desde esa tarjeta, confirma. El modelo no tiene ninguna herramienta de confirmación.
- Al confirmar, el servidor comprueba firma, caducidad, cuenta y usuario. Cualquier fallo o excepción es un rechazo (fallo cerrado).
- La confirmación ejecuta el mismo caso de uso que el formulario, con las mismas reglas: RN-F-10 rechaza un cobro superior al pendiente y RN-F-11 pide confirmar si se supera lo pendiente, también cuando propone el agente.
- Cada `PendingAction` se ejecuta una sola vez. Confirmarla dos veces, o un doble clic, no repite la operación.
- La confirmación queda en `audit_events` con el actor «agente con confirmación» (RF-FA-08).
- Un corte del SSE nunca ejecuta una escritura.
- La duración de la caducidad se fija en el Bloque 6.

## Consecuencias

- **Positivas:**
  - Cumple RN-04 por diseño, no por el comportamiento del modelo.
  - Limita el daño de una inyección de instrucciones: como mucho aparece una propuesta que el usuario ve y descarta (ADR-019).
  - El registro de eventos distingue lo que hizo el usuario de lo que propuso el agente.
- **Negativas y mitigación:**
  - Un paso más para el usuario. Se mitiga con una tarjeta clara que muestra el borrador completo (ui-ux).
  - La clave HMAC es un secreto más. Se guarda fuera del repo y de las imágenes (ADR-022, plataforma-entrega).
  - Hay que guardar qué propuestas se han ejecutado para la idempotencia. Es una tabla pequeña con la cuenta fijada (ADR-024).
- **Qué haría reconsiderarla:** que la interfaz deje de ser la única vía de uso (por ejemplo, una integración sin pantalla), o que la ley o el producto permitan escrituras automáticas sin revisión humana.

## Verificación

- `test_llm06_ninguna_herramienta_escribe_directamente`: recorre el registro de herramientas y comprueba que las de escritura solo devuelven `PendingAction` (`@pytest.mark.req("RN-04")`, `@pytest.mark.owasp("LLM06")` si se confirma el marcador para LLM, ver ADR-021).
- `test_llm06_pending_action_caducada` y `test_a04_firma_alterada_rechazada` (`req("RN-04")`, `owasp("A04")`).
- `test_a10_verificacion_falla_cerrada`: una excepción al verificar la firma equivale a rechazo.
- Prueba de idempotencia: una `PendingAction` confirmada dos veces, y un doble clic en Confirmar, emiten una sola factura.
- Escenario «Presupuesto por voz con precios del histórico»: el presupuesto no se guarda hasta pulsar Confirmar (`req("RF-PR-03")`).
- Regla Semgrep `comparacion-de-firma-con-==` en CI.
- Prueba de caos: cierre del navegador con una `PendingAction` abierta.
