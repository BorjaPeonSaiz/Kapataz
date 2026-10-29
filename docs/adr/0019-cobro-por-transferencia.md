# ADR-0019: Cobro mensual por transferencia bancaria

- **Estado:** Aceptada; modificada por [ADR-0020](0020-modo-sin-ia-y-notificaciones.md) (recordatorios por email y solo lectura por impago)
- **Fecha:** 2026-10-29

## Contexto

El plan preveía cobrar las suscripciones con Stripe y Laravel Cashier. Con un precio de 20 € al mes (IVA incluido), las comisiones de una pasarela de pago serían un porcentaje apreciable de cada cobro. Al principio el número de clientes será bajo y se puede gestionar el cobro a mano.

## Decisión

- Los clientes pagan la cuota **mensual por transferencia bancaria**. No hay pasarela de pago digital en el MVP.
- Cada empresa tiene una **referencia de pago única** (por ejemplo, `SAAS-000123`) que debe indicar en el concepto de la transferencia.
- La plataforma genera cada mes un **periodo de cobro** por empresa (importe, vencimiento y estado `pending`, `paid` u `overdue`) y su **factura de la cuota**, que la empresa ve y descarga desde su cuenta. Esa factura cumple los mismos requisitos fiscales que cualquier otra ([ADR-0011](0011-bloqueo-documentos-enviados.md)).
- El `admin` **marca los pagos como recibidos** desde el panel interno, tras comprobarlos en el banco. Queda registrado quién, cuándo y con qué referencia.
- **Recordatorios** automáticos por email antes del vencimiento y cuando el pago está vencido.
- **Impago:** pasados N días del vencimiento (configurable, inicialmente 15), la empresa pasa a **solo lectura**: puede consultar y descargar sus datos, pero no subir documentos ni usar el agente. Nunca se borran datos por impago. Al registrar el pago se reactiva al momento.
- La tabla `subscriptions` con identificadores de Stripe se sustituye por `billing_periods` (tenant_id, period, amount, vat, due_date, status, payment_reference, paid_at, marked_paid_by, invoice_id).

## Alternativas consideradas

- **Stripe con tarjeta:** cobro automático, pero con comisión por cobro y más integración que el MVP no necesita.
- **Domiciliación SEPA (recibos):** cobro automático y comisiones bajas, pero requiere mandato firmado y un acuerdo con el banco o un proveedor. Es la evolución natural cuando el volumen de clientes haga pesada la conciliación manual.

## Consecuencias

- Ahorro de las comisiones de la pasarela.
- Trabajo manual de conciliación para el `admin`: unos minutos por cliente al mes. Con unos 100 clientes conviene automatizarlo (importación del extracto bancario o domiciliación SEPA), con un ADR nuevo.
- Más riesgo de retrasos e impagos que con un cobro automático; lo mitigan los recordatorios y el paso a solo lectura.
- La plataforma emite sus propias facturas de cuota, así que también le aplican las obligaciones de facturación (numeración, conservación y, cuando sea obligatorio, VeriFactu).
