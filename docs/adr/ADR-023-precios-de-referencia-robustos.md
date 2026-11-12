# ADR-023 — Precios de referencia robustos

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-06, RN-07, RN-08, RN-10, RF-CO-04, RF-PR-02, RF-CF-02
- **Se cierra en:** Bloque 7

## Contexto

El agente propone precios a partir del histórico del profesional: «¿qué suelo cobrar por cambiar un cuadro eléctrico?» o un presupuesto con «tres puntos de luz». Ese precio de referencia entra en presupuestos que el profesional envía a sus clientes, así que un valor malo cuesta dinero.

El histórico tiene ruido: una factura con un precio absurdo, un error de extracción que se coló, un trabajo especial cobrado muy por encima de lo normal o un descuento puntual. Además, una factura importada puede estar diseñada para envenenar el precio (OWASP LLM04).

RN-07 fija la regla: el precio habitual es la mediana sin atípicos (MAD), se muestra con su número de muestras y su rango, y con menos de 3 muestras se avisa y no se propone de forma automática. RN-06 exige que todo precio propuesto indique su origen. RN-08 dice que solo cuentan los documentos revisados y aprobados.

## Opciones consideradas

1. **Media aritmética.**
   - Ventajas: sencilla y conocida.
   - Inconvenientes: un solo atípico la mueve; es la más fácil de envenenar.
2. **Mediana simple.**
   - Ventajas: robusta frente a atípicos aislados; fácil de explicar.
   - Inconvenientes: el rango (mínimo y máximo) sigue mostrando los atípicos; con pocas muestras sigue siendo frágil.
3. **Mediana tras excluir atípicos por MAD (desviación absoluta mediana), con muestras mínimas.**
   - Ventajas: robusta también en el rango; el criterio de exclusión es explicable; encaja con RN-07.
   - Inconvenientes: hay que fijar el umbral de exclusión; con muy pocas muestras la MAD no es fiable.
4. **Exclusión por rango intercuartílico (IQR) o recorte por percentiles.**
   - Ventajas: métodos estándar y robustos.
   - Inconvenientes: necesitan más muestras que la MAD para ser estables; RN-07 ya nombra la MAD.

## Decisión

Propuesta: opción 3, que es la que fija RN-07.

- El precio de referencia se calcula en el dominio (`catalog`) como función pura sobre `Decimal`, nunca con `float` (RN-01).
- Solo entran líneas de documentos revisados y aprobados, de la cuenta actual (RN-08, RN-10).
- Se excluyen los atípicos por MAD y se calcula la mediana del resto.
- Se devuelve el precio con su número de muestras, su rango y su origen (catálogo, mediana del histórico o presupuesto similar concreto, RN-06).
- Con menos de 3 muestras se avisa y no se propone de forma automática. Sin origen, la línea queda sin precio y marcada (RN-06).
- Excluir o borrar un documento recalcula los precios que dependían de él en la misma transacción (RN-08).

## Consecuencias

- **Positivas:**
  - Un atípico o una factura envenenada no mueve el precio propuesto.
  - El profesional ve de dónde sale cada precio y con cuántas muestras.
- **Negativas y mitigación:**
  - Con pocas muestras no hay propuesta automática. Se mitiga con el catálogo editable (RF-CF-02), que el profesional rellena a mano.
  - La MAD puede excluir precios legítimos de trabajos especiales. Se mitiga mostrando el rango y las muestras y dejando que el profesional corrija el precio.
- **Qué haría reconsiderarla:** que con los datos sintéticos o con las pruebas de Borja la mediana sin atípicos dé precios que el profesional no reconoce como suyos.

## Pendiente para cerrar

Se decide en el Bloque 7 con los datos sintéticos del Bloque 3 y con el criterio de Borja:

- **Umbral de exclusión por MAD:** cuántas MAD desde la mediana se consideran atípico. Se elige probándolo sobre los datos sintéticos con atípicos sembrados.
- **Qué es «el mismo concepto»:** si se agrupan líneas por `CatalogItem`, por texto normalizado o por similitud (búsqueda del Bloque 5), y qué pasa con unidades distintas (unidad, metro, hora).
- **Rango:** RF-CO-04 pide mediana, mínimo, máximo y número de apariciones, y RN-07 pide número de muestras y rango. Falta decidir si el mínimo y el máximo se calculan antes o después de excluir atípicos, y si se muestra cuántos se excluyeron.
- **Antigüedad:** si los precios antiguos pesan igual que los recientes o se limita el periodo.
- **Prioridad de orígenes:** qué gana cuando hay a la vez precio de catálogo, mediana del histórico y presupuesto similar.
- **Descuentos:** si se usa el precio unitario antes o después del descuento de línea.

## Verificación

- `test_llm04_atipico_no_altera_mediana` (`@pytest.mark.req("RN-07")`).
- `test_llm09_precio_incluye_muestras_y_rango` y `test_llm09_pocas_muestras_avisa` (`req("RN-07")`).
- `test_llm04_documento_en_revision_no_cuenta` y `test_llm04_excluir_documento_recalcula` (`req("RN-08")`).
- Prueba de propiedades con hypothesis: el precio no depende del orden de las muestras, nunca sale del rango de las muestras no excluidas y un único valor extremo añadido queda excluido.
- Escenario «Presupuesto por voz con precios del histórico»: la línea indica «mediana de 12 facturas» (`req("RN-06")`).
