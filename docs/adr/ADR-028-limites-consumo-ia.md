# ADR-028 — Límites de consumo de IA

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-UC-01, RF-UC-02, RF-SA-03, RNF-08, RN-12
- **Se cierra en:** Bloque 6

## Contexto

Claude va incluido en la cuota mensual y la clave de la API es de KodigoLab (ADR-005). Cada consulta, clasificación y extracción cuesta dinero, y todas usan `claude-opus-5-5`. Una cuenta abusiva, un bucle de herramientas o un error de programación pueden disparar la factura de Anthropic por encima de lo que se cobra (OWASP LLM10).

RF-UC-01 exige un límite mensual de uso de IA por cuenta, incluido en la cuota, y que el usuario vea su consumo. RF-UC-02 dice que al alcanzarlo la IA se pausa con un aviso y el resto de la app sigue funcionando. RF-SA-03 da al superadministrador el control de los límites por cuenta y del tope global de gasto. El primer paso del flujo del agente es comprobar el límite (§4.6).

## Opciones consideradas

1. **Sin límites, solo alertas de gasto.**
   - Ventajas: ninguna fricción para el usuario.
   - Inconvenientes: el coste no tiene techo; una sola cuenta puede consumir el margen de todas.
2. **Límite de peticiones por cuenta.**
   - Ventajas: fácil de explicar y de contar.
   - Inconvenientes: una extracción de un PDF largo y una pregunta corta cuentan igual; no refleja el coste real.
3. **Contabilidad por petición (tokens y coste), límite mensual por cuenta y tope global de gasto.**
   - Ventajas: refleja el coste real; protege a la plataforma aunque fallen los límites por cuenta.
   - Inconvenientes: hay que contabilizar bien cada petición, incluido el prompt caching, y elegir valores con datos.
4. **Pago por uso por encima de lo incluido.**
   - Ventajas: el uso intensivo se paga.
   - Inconvenientes: sorpresas en la factura del cliente, contrarias a HU-17; más complejidad de cobro.

## Decisión

Propuesta: opción 3.

- Cada petición a Claude registra en `ai_usage` los tokens y el coste, por cuenta.
- Antes de cada petición se comprueba el límite mensual de la cuenta y el tope global.
- Al alcanzar cualquiera de los dos, la IA se pausa con un aviso que muestra el consumo. Formularios, listados y PDF siguen funcionando (RF-UC-02, RNF-08).
- El usuario ve su consumo en su cuenta (RF-UC-01).
- El superadministrador ve el coste por cuenta y fija el límite por cuenta y el tope global (RF-SA-03). Los valores viven en `platform_settings`.
- Límites por turno del agente: iteraciones (por defecto 6), tokens de salida y tiempo.
- Prompt caching con un prefijo estable (sistema y herramientas) para bajar el coste.
- Alerta de gasto de IA con su runbook. Como segunda barrera, la clave tiene su propio espacio de trabajo y límite de gasto en la consola de Anthropic.
- Con la cuenta en solo lectura no se usa la IA (RN-12).

## Consecuencias

- **Positivas:**
  - El coste de la plataforma tiene techo.
  - Una cuenta no puede agotar el margen de las demás.
  - El usuario sabe cuánto ha consumido y que el resto de la app sigue funcionando.
- **Negativas y mitigación:**
  - Un usuario puede quedarse sin IA a mitad de mes. Se mitiga mostrando el consumo antes de llegar al límite y dejando intacto lo que no usa IA.
  - Un error en la contabilidad deja pasar coste. Se mitiga comparando `ai_usage` con los tokens que informa la API y con el límite de la consola de Anthropic.
- **Qué haría reconsiderarla:** que el coste medio por cuenta resulte muy inferior a la cuota (los límites sobran) o muy superior (hay que cambiar el precio o el modelo).

## Pendiente para cerrar

Se decide en el Bloque 6 con el coste medido en la evaluación de `claude-opus-5-5` (coste por consulta, por documento y por cuenta típica al mes, frente al precio de la cuota):

- **Unidad del límite:** tokens, coste en euros o una unidad propia que vea el usuario.
- **Valores:** límite mensual por cuenta y tope global de gasto. El plan no da cifras.
- **Qué cuenta:** si la clasificación y la extracción de la ingesta cuentan contra el mismo límite que el chat, y qué pasa con una ingesta a medias cuando se alcanza.
- **Petición en curso:** si una respuesta que cruza el límite se termina o se corta.
- **Inicio del mes:** mes natural o periodo de la suscripción.
- **Avisos previos:** si se avisa antes de llegar al límite y a partir de qué consumo.
- **Coste del caché:** cómo se contabilizan la escritura y la lectura del prompt caching.
- **Cuentas de cortesía y de demostración:** qué límite tienen (RF-SA-04, RN-13).

## Verificación

- Escenario «Límite de uso de IA»: con el límite agotado, el aviso muestra el consumo y se pueden crear facturas por formulario (`@pytest.mark.req("RF-UC-02")`).
- `test_llm10_limite_por_cuenta` y `test_llm10_tope_global` (`req("RF-UC-01")`).
- `test_llm10_bucle_cortado_por_limite`.
- Prueba de contabilidad: `ai_usage` coincide con los tokens que informa la API (con `FakeLlm` en CI y comprobado en la Fase 4).
- Escenario «Claude no responde» (`req("RNF-08")`).
- Alerta de gasto disparada al menos una vez a propósito (Fase 6).
