# ADR-0012: RAG híbrido con reranking

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Las facturas y presupuestos de una empresa se parecen mucho entre sí. La búsqueda solo vectorial tiende a devolver fragmentos casi iguales de documentos distintos, lo que produce citas incorrectas.

## Decisión

- La recuperación combina búsqueda vectorial (pgvector) y textual (`tsvector`) con Reciprocal Rank Fusion, siempre filtrada por `tenant_id` dentro de la consulta.
- Se recuperan 30-50 candidatos, un reranker (cross-encoder local como `bge-reranker` o una API como Cohere Rerank o Voyage) los reordena y al LLM solo llegan los mejores (por ejemplo, 5) que superen un umbral de relevancia.
- Las respuestas basadas en documentos incluyen citas con fichero y página. Las cifras y estados no se obtienen del RAG, sino de consultas estructuradas.
- El contenido recuperado se trata como dato no confiable: no puede cambiar las instrucciones ni los permisos del agente.

## Alternativas consideradas

- **Solo búsqueda vectorial:** peor precisión en documentos muy parecidos.
- **Sin reranker:** menos latencia, pero más citas incorrectas.

## Consecuencias

- Latencia y coste adicionales del reranker, que se miden (p95) y se limitan con el número de candidatos y el umbral.
- La suite de evaluación mide recall@k y precisión con y sin reranking.
