# ADR-016 — Suscripción con Stripe

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-PG-01, RF-PG-02, RF-PG-03, RF-PG-04, RF-SA-03, RF-SA-04, RF-SA-07, RN-12, RN-13
- **Se cierra en:** Bloque 10

## Contexto

Kapataz se cobra con una cuota mensual. El usuario paga con tarjeta o PayPal en la página de pago de la pasarela (RF-PG-01) y el acceso se abre cuando la pasarela confirma el pago (RF-PG-02). Puede ver sus recibos, cambiar el medio de pago y cancelar (RF-PG-03).

Reglas de impago y baja:

- Si un cobro falla, se avisa y se reintenta durante 14 días con la app completa (RF-PG-04).
- Después, o al terminar el periodo pagado tras una baja, la cuenta pasa 90 días a solo lectura y luego se borra (RN-12).
- El superadministrador fija los plazos de gracia y de solo lectura (RF-SA-03), crea cuentas de cortesía sin pago (RF-SA-04) y, con el registro cerrado, habilita emails concretos para probar el pago (RF-SA-07, RN-13).

Los datos de tarjeta nunca deben pasar por nuestro servidor.

## Opciones consideradas

1. **Stripe Checkout y Billing**, con tarjeta y PayPal, detrás de `SubscriptionPort`.
   - Ventajas: página de pago y portal de cliente alojados por Stripe; recibos, reintentos y cambios de medio de pago incluidos; los datos de tarjeta no tocan nuestro servidor; modo de pruebas.
   - Inconvenientes: dependencia de un proveedor y sus comisiones; el estado llega por webhooks, que pueden retrasarse o repetirse.
2. **Formulario de pago propio**
   - Ventajas: control total de la experiencia.
   - Inconvenientes: los datos de tarjeta pasan por nuestro servidor y amplían mucho las obligaciones de seguridad. Descartado.
3. **PayPal por un lado y otra pasarela para tarjetas**
   - Ventajas: sin intermediario para PayPal.
   - Inconvenientes: dos integraciones, dos conciliaciones y dos fuentes de verdad del estado de la suscripción.
4. **TPV virtual bancario**
   - Ventajas: contrato directo con el banco, sin otro intermediario.
   - Inconvenientes: cobros recurrentes, recibos y portal de cliente habría que construirlos.

## Decisión

Opción 1.

- `SubscriptionPort` → `StripeSubscriptions`; `FakeSubscriptions` en pruebas y hasta el Bloque 10.
- **El estado de la suscripción solo cambia por webhook**, nunca por lo que diga el navegador al volver de la página de pago.
- Webhooks con firma verificada; cada evento se guarda en `payment_events` y no se aplica dos veces.
- Plazos por defecto: 14 días de gracia y 90 días de solo lectura, configurables por el superadministrador en `platform_settings`.
- Cuentas de cortesía sin pago para demos y pruebas, creadas solo por el superadministrador.
- **Papel de Stripe ante el RGPD:** solo trata datos de los suscriptores; es encargado para el cobro y responsable independiente para fraude y cumplimiento normativo, según su contrato de tratamiento.

## Consecuencias

- **Positivas**
  - Sin datos de tarjeta en nuestro servidor.
  - Recibos, reintentos y portal de cliente sin construirlos.
  - Las pruebas no dependen de Stripe gracias a `FakeSubscriptions`.
- **Negativas y mitigación**
  - Webhooks retrasados → la interfaz muestra «pago pendiente de confirmar» hasta recibirlo.
  - Webhooks repetidos o desordenados → `payment_events` sin repetición y transiciones de estado validadas en el dominio.
  - Dependencia de Stripe → `SubscriptionPort` permite cambiar de pasarela sin tocar el dominio.
- **Qué haría reconsiderarla**
  - Que Stripe deje de ofrecer PayPal para la cuenta de KodigoLab.
  - Comisiones que no quepan en la cuota.

## Verificación

- **import-linter:** `stripe` solo se importa desde `kapataz.infrastructure.payments`.
- `tests/integration/payments/test_webhook_firma.py`: un webhook con firma inválida se rechaza y no cambia el estado. `@pytest.mark.req("RF-PG-02")`.
- `tests/integration/payments/test_webhook_repetido.py`: el mismo evento dos veces produce un solo efecto. `@pytest.mark.req("RF-PG-02")`.
- `tests/integration/payments/test_retorno_navegador.py`: volver de la página de pago sin webhook no abre el acceso. `@pytest.mark.req("RF-PG-02")`.
- `tests/integration/payments/test_gracia_y_solo_lectura.py` con `FrozenClock`: tras un cobro fallido, la app sigue completa durante los 14 días de gracia y después pasa a solo lectura; pasados 90 días se inicia el borrado. `@pytest.mark.req("RF-PG-04")` y `@pytest.mark.req("RN-12")`.
- **Escenarios** «Acceso tras pagar la cuota» y «Suscripción terminada».
- **Staging** con el modo de pruebas de Stripe; en el Bloque 10, pagos reales con tarjeta y con PayPal en cuentas habilitadas por el superadministrador (RN-13).
