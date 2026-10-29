# ADR-0003: PostgreSQL 16 con pgvector como base de datos única

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Usuarios, clientes, proveedores, facturas y presupuestos necesitan claves, restricciones, relaciones, transacciones y sumas exactas. El agente necesita además búsqueda semántica sobre el contenido de los documentos.

## Decisión

- **PostgreSQL 16** es la fuente de verdad para todos los datos de negocio y de auditoría.
- **pgvector** guarda los embeddings de los fragmentos de documentos en la misma base, con índice HNSW, junto a un índice GIN sobre `tsvector` para la búsqueda textual.
- Las cifras y los estados se obtienen siempre con consultas SQL tipadas, nunca por similitud vectorial.
- Los importes se guardan como `NUMERIC` con precisión definida y moneda ISO.

## Alternativas consideradas

- **Base de datos vectorial dedicada como base principal:** no ofrece integridad relacional ni transacciones para datos contables.
- **MySQL:** no aporta ventaja decisiva y obliga a resolver aparte la búsqueda vectorial.
- **PostgreSQL + base vectorial separada desde el inicio:** más piezas que operar sin necesidad con el volumen previsto.

## Consecuencias

- Un solo motor que operar, respaldar y asegurar con Row Level Security.
- Si el volumen de documentos lo exige, el índice vectorial podrá separarse más adelante sin migrar los datos transaccionales.
