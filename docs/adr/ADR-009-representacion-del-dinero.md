# ADR-009 — Representación del dinero

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Modificado:** 2026-11-18. Borja aprueba precisar el cálculo exacto con un solo redondeo, el tope de `Money` y las rutas de las pruebas. 2026-11-19: se documenta el CHECK `ck_invoices_amounts` como defensa en profundidad (cierre del Bloque 2, aprobado por Borja).
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-01, RN-02, RN-03, RF-CO-02, RF-FA-05, RF-FA-07, RN-F-05, RN-F-12, RN-F-13

## Contexto

Kapataz emite facturas legales. Un céntimo de diferencia entre base, cuota y total es un error fiscal, y el registro de facturación (RN-F-07) recoge los importes exactos.

Fuerzas:

- `float` no representa con exactitud importes decimales: `0.1 + 0.2` no es `0.3`.
- El redondeo debe ser a dos decimales por línea y por cuota, con ROUND_HALF_UP, y la suma de bases y cuotas debe cuadrar con el total (RN-03).
- Hay cálculos con divisiones: el anticipo de 6.000 € cobrado para una obra al 10 % tiene una base de 6.000 / 1,10 = 5.454,55 € y una cuota de 6.000 − 5.454,55 = 545,45 € (RN-F-12). Si se redondeara también la cuota por separado, el total podría no coincidir al céntimo con lo cobrado.
- Un LLM puede inventar o redondear cifras. El modelo nunca calcula importes (RN-02); toda cifra sale de una herramienta (RF-CO-02).

## Opciones consideradas

1. **`Decimal` en el dominio y céntimos `INTEGER` en la base de datos**, redondeo ROUND_HALF_UP por línea y por cuota.
   - Ventajas: cálculo exacto con reglas de redondeo explícitas; en la base de datos, los dos decimales son una propiedad del tipo; sumas en SQL exactas.
   - Inconvenientes: conversión en el borde de persistencia; `INTEGER` de PostgreSQL limita cada importe a 2.147.483.647 céntimos.
2. **`float` en todo el sistema**
   - Ventajas: ninguna relevante.
   - Inconvenientes: errores de representación; prohibido por RN-01.
3. **`Decimal` en el dominio y `NUMERIC(…, 2)` en la base de datos**
   - Ventajas: sin conversión; legible en SQL.
   - Inconvenientes: una columna mal definida admite más decimales sin avisar; la conversión a `Decimal` depende de la configuración del ORM.
4. **Céntimos enteros también en el dominio**
   - Ventajas: aritmética entera, sencilla.
   - Inconvenientes: porcentajes de IVA y retención y divisiones como la del anticipo obligan a redondeos manuales repartidos por el código; menos legible que `Decimal` con reglas de redondeo explícitas.

## Decisión

Opción 1.

- **`Money`** es un objeto de valor inmutable (dataclass `frozen`, `slots`) que solo acepta `Decimal`. Construirlo con `float` es un error.
- **Redondeo** a dos decimales por línea y por cuota con `ROUND_HALF_UP`, en un único módulo del dominio (`domain/billing`). La suma de bases y cuotas cuadra con el total.
- **Cálculo exacto:** los productos y divisiones intermedios se hacen con `Fraction`, sin pérdida, y cada importe se redondea una sola vez al final (`Money.round`). Con `Decimal`, una división como 6.000 / 1,10 se trunca a 28 dígitos antes de redondear y podría mover un céntimo.
- **Tope:** `Money` rechaza importes cuyo valor absoluto supere 21.474.836,47 €, el máximo de los céntimos en `INTEGER`. La factura lo comprueba al crear o editar el borrador, no al calcular sus totales.
- **Excepción de RN-03:** cuando se parte de un importe con IVA incluido, como el anticipo cobrado (RN-F-12), se redondea la base y la cuota es la diferencia entre ese importe y la base, para que el total coincida al céntimo con lo cobrado. Con 6.000 € al 10 %: base 5.454,55 € y cuota 545,45 €.
- **Base de datos:** importes en céntimos `INTEGER`. La conversión solo ocurre en los adaptadores de persistencia.
- **Defensa en profundidad:** las columnas de importe de `invoices` son una copia de lo que calcula el dominio, y la base de datos comprueba que cuadran con el CHECK `ck_invoices_amounts`: `total_amount = base_total + tax_total AND amount_due = total_amount - withholding_amount - guarantee_amount`. No calcula nada ni sustituye al dominio, que sigue siendo el único sitio donde se calcula y se redondea; solo impide guardar una copia incoherente, por un error de la app o por SQL directo. Al leer una emitida, el dominio vuelve a calcular sus importes de las líneas y los compara con los guardados (`IssuedAmounts`).
- **API:** devuelve importes ya calculados. El frontend no recalcula totales; solo los formatea con `Intl` en `es-ES`.
- **LLM:** si propone un total, se descarta y se recalcula (RN-02). Las cifras de la respuesta se renderizan desde el resultado de la herramienta (§4.6).

## Consecuencias

- **Positivas**
  - Importes exactos y un solo sitio donde se calcula y se redondea.
  - Las pruebas de propiedades cubren cualquier combinación de líneas.
- **Negativas y mitigación**
  - Conversión entre `Decimal` y céntimos → un único conversor en persistencia, con pruebas de ida y vuelta.
  - Límite de `INTEGER` (unos 21,4 millones de euros por importe) → suficiente para las facturas de un autónomo; las sumas de PostgreSQL sobre `INTEGER` devuelven `BIGINT`. Si hiciera falta, se migra la columna a `BIGINT`.
  - Un segundo cálculo de importes en otra capa → `revisor-codigo` lo busca como duplicación bloqueante.
- **Qué haría reconsiderarla**
  - Necesitar precios unitarios con más de dos decimales guardados tal cual.
  - Facturar en otra moneda.

## Verificación

- `tests/unit/domain/test_value_objects.py`: `Money` rechaza un `float`. `@pytest.mark.req("RN-01")`.
- `tests/unit/domain/test_totales_propiedades.py` con hypothesis: para cualquier combinación de líneas, la suma de bases y cuotas cuadra con el total. `@pytest.mark.req("RN-03")`.
- `tests/unit/domain/test_calculation.py` y `test_invoice.py`: 6.000 € al 10 % dan 5.454,55 € de base y 545,45 € de cuota, y el total es 6.000,00 €. `@pytest.mark.req("RN-F-12")`, `@pytest.mark.req("RN-03")`.
- `tests/unit/agent/test_total_del_modelo_se_descarta.py`: un total propuesto por `FakeLlm` se ignora y se recalcula. `@pytest.mark.req("RN-02")`.
- `tests/integration/persistence/test_conversion_centimos.py`: ida y vuelta entre `Decimal` y céntimos sin pérdida. `@pytest.mark.req("RN-01")`.
- `tests/unit/domain/test_fases_propiedades.py` con hypothesis: sin trabajos adicionales, la suma de las fases cuadra al céntimo con el presupuesto. `@pytest.mark.req("RN-F-12")`.
- Una factura cuyo total supera el tope se rechaza al crear el borrador. `@pytest.mark.req("RN-01")`.
- `tests/integration/persistence/test_repositorios.py`: un `UPDATE` por SQL que descuadra el total, la cuota o el importe a cobrar choca con `ck_invoices_amounts`. `@pytest.mark.req("RN-03")`.
- **mypy `--strict`:** la firma de `Money` solo admite `Decimal`.
- **mutmut** sobre `domain/billing`.
- **CI:** regla propia de Semgrep que marca `float(` en `domain/billing`.
