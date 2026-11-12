# ADR-020 — Datos sintéticos para demo y pruebas

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-CF-04, RN-F-09, RN-13, RN-05, RNF-06, RNF-07, RNF-17, RF-IN-05
- **Se cierra en:** Bloque 3

## Contexto

Kapataz necesita datos para cuatro cosas: la demo pública, el modo demostración de cada cuenta (RF-CF-04), las pruebas automáticas y los datasets de evaluación de la IA (RNF-06, RNF-07, RNF-17). Hasta publicar la 1.0.0, las cuentas solo trabajan en el espacio de demostración (RN-13).

Esos datos tienen que parecer reales: maquetaciones de PDF distintas, errores típicos, nombres que se repiten, IVA general y reducido, inversión del sujeto pasivo y retenciones. Pero no pueden ser de nadie: usar facturas reales metería datos personales en el repo, en CI y en lo que se envía a Claude.

## Opciones consideradas

1. **Facturas reales anonimizadas** (propias o de conocidos).
   - Ventajas: realismo máximo en maquetación y conceptos.
   - Inconvenientes: datos personales en el repo y en CI; la anonimización manual falla; no se pueden sembrar errores a voluntad ni tener verdad de referencia exacta.
2. **Datos escritos a mano.**
   - Ventajas: control total de cada caso.
   - Inconvenientes: pocos documentos, poca variación y mucho trabajo para 18 meses de actividad.
3. **Datos generados por un LLM.**
   - Ventajas: textos variados con poco esfuerzo.
   - Inconvenientes: no determinista, con coste por ejecución y sin garantía de que las cifras cuadren donde deben cuadrar.
4. **Generador propio con Faker `es_ES` y reglas de oficio, determinista con semilla.**
   - Ventajas: reproducible, sin datos de nadie, con errores sembrados conocidos y con su JSON esperado.
   - Inconvenientes: hay que escribir y mantener el generador y las plantillas de PDF.

## Decisión

Se elige la opción 4.

- `tools/gen_synthetic.py` genera dos profesionales ficticios: un electricista autónomo en Cantabria y un albañil que trabaja para constructoras (inversión del sujeto pasivo, retenciones).
- Cada uno con 18 meses de actividad, 40–60 facturas y 20–30 presupuestos. Clientes particulares, comunidades de vecinos y empresas, con nombres repetidos a propósito para probar la ambigüedad (RF-CO-05).
- Conceptos de oficio con precios coherentes y variación realista.
- Cinco maquetaciones de PDF: tabla clásica, Word exportado, plantilla de programa genérico, texto sin tabla, y con logotipo y pie extensos.
- Imperfecciones sembradas: totales con errores, IVA mal calculado, NIF ausente y líneas partidas entre páginas.
- Un PDF trampa con instrucciones inyectadas (RN-05, ADR-019).
- Cada PDF va con su JSON esperado en `evals/extraction/`. Los PDFs se versionan en `samples/`.
- El generador es determinista con semilla: la misma semilla produce los mismos datos.
- `seed_demo.py` carga el modo demostración. Las facturas del espacio de demostración llevan siempre la marca «Documento de demostración» (RN-F-09).

## Consecuencias

- **Positivas:**
  - Ningún dato real en el repo, en CI ni en las evaluaciones con Claude.
  - Verdad de referencia exacta para medir la extracción y las fugas de la seudonimización.
  - La demo se puede regenerar en cualquier momento.
- **Negativas y mitigación:**
  - Los datos sintéticos pueden ser más «limpios» que los reales. Se mitiga con las imperfecciones sembradas y con varias maquetaciones; si la Fase 4 detecta sesgo, se añaden plantillas.
  - Un NIF generado con dígito de control válido puede coincidir con el de una persona real. Se mitiga generándolo siempre junto a nombres ficticios y solo en espacios de demostración y pruebas.
- **Qué haría reconsiderarla:** que la precisión medida con datos sintéticos no se parezca a la que observa Borja con sus propios documentos en pruebas manuales.

## Verificación

- Prueba de determinismo del generador: dos ejecuciones con la misma semilla producen el mismo contenido (`@pytest.mark.req("RF-CF-04")`).
- Prueba de completitud: todo PDF de `samples/` tiene su JSON en `evals/extraction/`.
- Escenario «Primer arranque»: se cargan datos de ejemplo en un espacio separado (`req("RF-CF-04")`).
- Escenario «Extracción que no cuadra» sobre un PDF con total erróneo sembrado (`req("RF-IN-05")`).
- gitleaks en CI y comprobación de la Fase 7 de que los PDFs de `samples/` son sintéticos.
- Criterio de terminado del Bloque 3: `samples/` y `evals/extraction/` versionados.
