# ADR-017 — Separación entre histórico importado y facturas emitidas

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-IN-06, RF-IN-08, RF-IN-09, RF-CO-02, RF-CO-03, RF-CO-04, RN-07, RN-08, RN-F-01, RN-F-02, RN-F-07, RN-F-08, RN-F-13
- **Se cierra en:** Bloque 2

## Contexto

El usuario importa facturas y presupuestos de antes de usar la app (RF-IN-01). Esos documentos los emitió otro sistema, con su propia numeración, y puede que con varios tipos de IVA en una misma factura.

Fuerzas:

- El histórico es de solo lectura: no se renumera ni se mezcla con la serie emitida por la app (RF-IN-09, RN-F-08).
- Las reglas de las facturas emitidas no aplican al histórico: numeración sin huecos (RN-F-01), inmutabilidad por trigger (RN-F-02), cadena de `BillingRecord` (RN-F-07) y un solo tipo de IVA por factura (RN-F-13). El histórico conserva sus facturas como son.
- Las consultas sí necesitan los dos: total facturado, precio habitual y trabajos parecidos (RF-CO-04, RN-07), citando cada fuente (RF-CO-03).
- Solo cuenta lo revisado y aprobado; excluir un documento lo retira de todo en la misma transacción (RN-08).

## Opciones consideradas

1. **Tablas distintas** (`historical_invoices` y `historical_lines`, separadas de `invoices` e `invoice_lines`); las consultas agregan ambas con el origen marcado.
   - Ventajas: las reglas fiscales de las emitidas no necesitan excepciones; imposible que un documento importado entre en la serie o en la cadena; esquemas libres de adaptarse a cada caso.
   - Inconvenientes: estructuras de línea parecidas en dos sitios; cada consulta agregada debe unir las dos fuentes.
2. **Una sola tabla `invoices` con una columna de origen**
   - Ventajas: una sola consulta para agregar.
   - Inconvenientes: cada regla (numeración, trigger, cadena, tipo único de IVA) necesita una excepción por origen; un error en una de ellas mete histórico en la serie o en la cadena.
3. **Histórico solo como extracciones**, sin tablas normalizadas
   - Ventajas: nada que duplicar.
   - Inconvenientes: agregaciones sobre JSON, sin índices útiles; consultas lentas y frágiles.

## Decisión

Opción 1.

- Al aprobar una extracción (RF-IN-06), sus datos pasan a `historical_invoices` y `historical_lines`, enlazados con su `source_documents` para citarlos.
- El histórico no usa `series_counters`, no genera `billing_records` y no tiene los triggers de factura emitida. Solo se puede excluir o borrar, con recálculo en la misma transacción (RN-08).
- Los clientes son comunes a ambos y se deduplican por NIF o por similitud confirmada (RF-IN-08).
- Las consultas agregadas combinan las dos fuentes en un único módulo de persistencia. Cada resultado lleva su origen (emitida por la app o histórico) y el enlace a su documento.
- Las dos fuentes comparten objetos de valor del dominio (`LineItem`, `Money`), no tablas.

El Bloque 2 cierra este ADR con las migraciones y las pruebas.

## Consecuencias

- **Positivas**
  - Las garantías fiscales de las emitidas no dependen de filtrar bien el origen.
  - El histórico puede guardar lo que hay en el documento, aunque no cumpla las reglas actuales.
- **Negativas y mitigación**
  - Dos estructuras de línea → mismos objetos de valor y un único conversor por tabla.
  - Olvidar el histórico en una consulta → un solo módulo de agregación con pruebas que incluyen ambas fuentes.
- **Qué haría reconsiderarla**
  - Que las consultas agregadas sean demasiado lentas al unir las dos fuentes.
  - Que la normativa obligue a tratar el histórico importado como parte del sistema de facturación.

## Verificación

- `tests/integration/documents/test_historico_no_toca_serie.py`: aprobar una factura histórica numerada «F-2025-0099» no cambia `series_counters` ni el siguiente número de la serie F. `@pytest.mark.req("RN-F-08")`.
- `tests/integration/documents/test_historico_sin_registro.py`: aprobar una factura histórica no genera ningún `BillingRecord`. `@pytest.mark.req("RN-F-08")`.
- `tests/integration/documents/test_historico_solo_lectura.py`: no hay caso de uso ni endpoint que modifique una factura histórica aprobada; solo excluirla. `@pytest.mark.req("RF-IN-09")`.
- `tests/integration/queries/test_total_facturado_dos_fuentes.py`: `total_facturado` suma emitidas e histórico, y cada fuente lleva su origen y su enlace. `@pytest.mark.req("RF-CO-03")`.
- `tests/integration/queries/test_exclusion_recalcula.py`: excluir un documento lo retira de totales, precios y búsqueda en la misma transacción. `@pytest.mark.req("RN-08")`.
