# Registro de decisiones de arquitectura (ADR)

Cada ADR sigue la plantilla del Anexo A del [plan maestro](../00-plan-maestro.md). Los que están en «Propuesto» se cierran en el bloque indicado; un ADR «Aceptado» con bloque posterior se confirma allí con datos.

Ningún ADR aceptado cambia sin que `arquitecto-python` lo proponga y Borja lo apruebe.

| ADR | Título | Estado | Se cierra en |
|---|---|---|---|
| [ADR-001](ADR-001-arquitectura-hexagonal-ligera.md) | Arquitectura hexagonal ligera | Aceptado | Bloque 0 |
| [ADR-002](ADR-002-python-fastapi-backend.md) | Python + FastAPI como backend | Aceptado | Bloque 0 |
| [ADR-003](ADR-003-uv-gestor-entorno-dependencias.md) | uv como gestor de entorno y dependencias | Aceptado | Bloque 0 |
| [ADR-004](ADR-004-postgresql-base-de-datos.md) | PostgreSQL como base de datos | Aceptado | Bloque 0 |
| [ADR-005](ADR-005-claude-como-llm.md) | Claude como LLM | Propuesto | Bloque 6 |
| [ADR-006](ADR-006-bucle-agente-propio.md) | Bucle de agente propio sin frameworks | Aceptado | Bloque 0 |
| [ADR-007](ADR-007-busqueda-hibrida-postgresql-pgvector.md) | Búsqueda híbrida con PostgreSQL y pgvector | Aceptado | Bloque 5 |
| [ADR-008](ADR-008-llm-falso-en-ci.md) | LLM falso determinista en CI; evaluaciones con Claude real fuera de CI | Aceptado | Bloque 0 |
| [ADR-009](ADR-009-representacion-del-dinero.md) | Representación del dinero | Aceptado | Bloque 0 |
| [ADR-010](ADR-010-lectura-generacion-pdf.md) | Lectura y generación de PDF | Aceptado | Bloque 0 |
| [ADR-011](ADR-011-voz-faster-whisper.md) | Voz con faster-whisper en nuestro servidor | Aceptado | Bloque 0 |
| [ADR-012](ADR-012-facturacion-verifactu.md) | Facturación conforme a Verifactu | Propuesto | Bloque 12 |
| [ADR-013](ADR-013-vue-servido-por-fastapi.md) | Vue 3 servido por FastAPI detrás de un proxy TLS | Aceptado | Bloque 0 |
| [ADR-014](ADR-014-despliegue-docker-compose-vps-ue.md) | Despliegue con Docker Compose en un VPS de la UE | Aceptado | Bloque 10 |
| [ADR-015](ADR-015-logs-estructurados-sin-datos-personales.md) | Logs estructurados sin datos personales | Aceptado | Bloque 0 |
| [ADR-016](ADR-016-suscripcion-stripe.md) | Suscripción con Stripe | Aceptado | Bloque 10 |
| [ADR-017](ADR-017-historico-separado-de-emitidas.md) | Separación entre histórico importado y facturas emitidas | Aceptado | Bloque 2 |
| [ADR-018](ADR-018-confirmacion-humana-escrituras-agente.md) | Confirmación humana obligatoria para escrituras del agente | Aceptado | Bloque 6 |
| [ADR-019](ADR-019-defensa-inyeccion-instrucciones.md) | Defensa ante inyección de instrucciones | Aceptado | Bloque 6 |
| [ADR-020](ADR-020-datos-sinteticos.md) | Datos sintéticos para demo y pruebas | Aceptado | Bloque 3 |
| [ADR-021](ADR-021-trazabilidad-owasp.md) | Trazabilidad de OWASP | Aceptado | Bloque 0 |
| [ADR-022](ADR-022-cadena-de-suministro.md) | Cadena de suministro | Aceptado | Bloque 1 |
| [ADR-023](ADR-023-precios-de-referencia-robustos.md) | Precios de referencia robustos | Propuesto | Bloque 7 |
| [ADR-024](ADR-024-multitenencia-rls.md) | Multitenencia con Row Level Security | Aceptado | Bloque 0 |
| [ADR-025](ADR-025-autenticacion-sesiones-cookie.md) | Autenticación propia con sesiones en cookie | Aceptado | Bloque 0 |
| [ADR-026](ADR-026-cola-tareas-postgresql.md) | Cola de tareas en PostgreSQL | Aceptado | Bloque 4 |
| [ADR-027](ADR-027-pwa-unica-app-movil.md) | PWA como única app móvil | Aceptado | Bloque 0 |
| [ADR-028](ADR-028-limites-consumo-ia.md) | Límites de consumo de IA | Propuesto | Bloque 6 |
| [ADR-029](ADR-029-tratamiento-datos-anthropic.md) | Tratamiento de datos con Anthropic | Aceptado | Bloque 0 |
| [ADR-030](ADR-030-seudonimizacion-antes-de-claude.md) | Seudonimización antes de Claude | Propuesto | Bloque 6 |
| [ADR-031](ADR-031-zona-superadministracion.md) | Zona de superadministración | Aceptado | Bloque 0 |
| [ADR-032](ADR-032-versionado-semantico.md) | Versionado semántico desde la 1.0.0 | Aceptado | Bloque 0 |
| [ADR-033](ADR-033-facturacion-por-fases.md) | Facturación por fases y trabajos adicionales | Propuesto | Bloque 8 |
