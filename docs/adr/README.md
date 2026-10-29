# Registro de decisiones de arquitectura (ADR)

Cada ADR recoge una decisión relevante: el contexto, lo que se decidió, las alternativas descartadas y sus consecuencias. Los ADR iniciales se han generado a partir del [plan de construcción](../proyecto/plan-de-construccion.md).

## Cómo añadir uno

1. Copia [0000-plantilla.md](0000-plantilla.md) con el siguiente número libre y un título corto en minúsculas con guiones.
2. Rellénalo con estado `Propuesta`. Cuando se apruebe, pasa a `Aceptada`.
3. Un ADR aceptado no se edita: si la decisión cambia, se crea uno nuevo y el antiguo pasa a `Sustituida por ADR-XXXX`.
4. Añádelo a la tabla de abajo.

## Índice

| ADR | Título | Estado |
| --- | --- | --- |
| [0001](0001-registro-de-decisiones.md) | Registrar las decisiones de arquitectura con ADR | Aceptada |
| [0002](0002-arquitectura-laravel-fastapi.md) | Laravel para la web y FastAPI para el agente y la ingesta | Aceptada |
| [0003](0003-postgresql-pgvector.md) | PostgreSQL 16 con pgvector como base de datos única | Aceptada |
| [0004](0004-agente-unico-comun.md) | Un único agente de IA común para todas las empresas | Aceptada |
| [0005](0005-aislamiento-multi-tenant.md) | Aislamiento total entre empresas | Aceptada |
| [0006](0006-roles-admin-cliente.md) | Dos roles y un único usuario por empresa | Aceptada |
| [0007](0007-google-drive-por-empresa.md) | Google Drive propio de cada empresa con OAuth `drive.file` | Aceptada |
| [0008](0008-entrada-solo-desde-la-aplicacion.md) | Los documentos solo entran por «Subir archivos» | Aceptada |
| [0009](0009-copia-privada-y-fuente-de-verdad.md) | Copia privada en S3 y PostgreSQL como fuente de verdad | Aceptada |
| [0010](0010-clasificacion-y-por-clasificar.md) | Archivado por carpetas y resolución manual de «Por clasificar» | Aceptada |
| [0011](0011-bloqueo-documentos-enviados.md) | Facturas y presupuestos bloqueados tras el envío | Aceptada |
| [0012](0012-rag-hibrido-con-reranking.md) | RAG híbrido con reranking | Aceptada |
| [0013](0013-observabilidad.md) | Logs JSON y trazas de LLM autoalojadas en la UE | Aceptada |
| [0014](0014-mcp-post-mvp.md) | Servidor MCP después del MVP | Aceptada |
| [0015](0015-python-extrae-laravel-persiste.md) | Python extrae y devuelve los datos; Laravel los guarda | Aceptada |
| [0016](0016-versionado-automatico.md) | Versionado automático en cada cambio a main y versión visible en el footer | Aceptada |
| [0017](0017-desarrollo-guiado-por-tests.md) | Desarrollo guiado por tests (TDD) | Aceptada |
| [0018](0018-estrategia-de-escalado.md) | Estrategia de escalado | Aceptada |
| [0019](0019-cobro-por-transferencia.md) | Cobro mensual por transferencia bancaria | Aceptada; modificada por ADR-0020 |
| [0020](0020-modo-sin-ia-y-notificaciones.md) | Impago sin corte de acceso (solo se desactiva la IA) y email únicamente para recuperar la contraseña | Aceptada |
| [0021](0021-copias-de-seguridad.md) | Copias de seguridad con pgBackRest en el VPS y Backblaze B2 gratuito | Aceptada |
| [0022](0022-panel-de-configuracion.md) | Panel de configuración de la plataforma para el `admin` | Aceptada |
