# ADR-007 — Búsqueda híbrida con PostgreSQL y pgvector

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-CO-03, RF-CO-04, RF-PR-02, RN-06, RN-08, RN-10, RNF-01, RNF-13
- **Se cierra en:** Bloque 5

## Contexto

El agente busca trabajos parecidos (`buscar_trabajos_similares`, RF-CO-04) y propone presupuestos a partir de otros similares (RF-PR-02). Las consultas mezclan dos tipos de texto:

- Nombres propios y términos exactos: clientes, calles, «magnetotérmico», «diferencial».
- Descripciones libres que cambian de palabras: «baño completo», «cuadro eléctrico comunidad».

Una búsqueda solo por vectores falla con los nombres exactos; una solo por texto falla con las paráfrasis.

Restricciones:

- Anthropic no ofrece embeddings. Usar otro proveedor añadiría a alguien más que trata datos (RNF-01).
- Ninguna búsqueda cruza datos entre cuentas (RN-10, RNF-13).
- Solo cuentan los documentos revisados y aprobados; retirar uno lo saca de todo en la misma transacción (RN-08).

## Opciones consideradas

1. **Híbrida en PostgreSQL:** búsqueda de texto en español con `unaccent` más pgvector, fusionadas con RRF; embeddings con un modelo abierto multilingüe en nuestro servidor (fastembed, ONNX en CPU).
   - Ventajas: un solo almacén; RLS también protege los fragmentos; filtros por cuenta y metadatos en SQL; la retirada de un documento entra en la misma transacción; ningún proveedor nuevo.
   - Inconvenientes: los embeddings consumen CPU del servidor; la calidad del modelo abierto y la fusión hay que medirlas y ajustarlas.
2. **Solo vectores**
   - Ventajas: más sencilla; buena con paráfrasis.
   - Inconvenientes: falla con nombres propios y términos exactos.
3. **Solo búsqueda de texto**
   - Ventajas: sin embeddings ni CPU extra.
   - Inconvenientes: falla con sinónimos y descripciones distintas del mismo trabajo.
4. **Base de datos vectorial aparte y embeddings por API externa**
   - Ventajas: servicio especializado.
   - Inconvenientes: otro servicio que operar y copiar; aislamiento fuera de RLS; los textos salen hacia otro proveedor.

## Decisión

Opción 1.

- `SearchPort` → `HybridPostgresSearch` (texto + pgvector + RRF).
- `EmbeddingPort` → `LocalEmbeddings` (fastembed); `FakeEmbeddings` en CI (ADR-008).
- Tabla `chunks` con columnas `tsvector` y `vector`, con `tenant_id` y política RLS.
- Troceado por documento y por línea significativa, con metadatos: cliente, fecha, tipo e importe.
- Indexación incremental al aprobar un documento; la retirada lo elimina en la misma transacción.

El enfoque queda aceptado. El Bloque 5 completa este ADR con los resultados: modelo de embeddings elegido por evaluación, recall@5 y MRR, y tiempo de reindexado.

## Consecuencias

- **Positivas**
  - Precisión con nombres propios y con descripciones libres.
  - El aislamiento y la coherencia con RN-08 los da la base de datos.
  - Los textos no salen del servidor para indexarse.
- **Negativas y mitigación**
  - CPU compartida con OCR y Whisper → embeddings en el worker (ADR-026), indexación incremental.
  - Calidad del modelo abierto → se elige por evaluación en el Bloque 5, con umbral recall@5 ≥ 0,85.
- **Qué haría reconsiderarla**
  - No alcanzar recall@5 ≥ 0,85 con ningún modelo abierto evaluado.
  - Que el reindexado completo de la demo supere 2 min en el servidor de referencia.

## Verificación

- **import-linter:** `fastembed` solo se importa desde `kapataz.infrastructure.embeddings`.
- `tests/integration/search/test_aislamiento_busqueda.py`: la cuenta A no recupera fragmentos de la B. `@pytest.mark.req("RN-10")`.
- `tests/integration/search/test_retirada_documento.py`: excluir un documento elimina sus fragmentos en la misma transacción. `@pytest.mark.req("RN-08")`.
- `tests/integration/search/test_busqueda_hibrida.py`: con `FakeEmbeddings` de vectores fijados por la prueba, la fusión RRF devuelve tanto el documento que solo encuentra la búsqueda de texto como el que solo encuentra la vectorial. `@pytest.mark.req("RF-CO-04")`.
- **Evaluación de recuperación** en el Bloque 5: recall@5 ≥ 0,85 y MRR sobre consultas de referencia; reindexado de la demo < 2 min.
