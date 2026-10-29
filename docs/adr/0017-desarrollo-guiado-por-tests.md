# ADR-0017: Desarrollo guiado por tests (TDD)

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

El producto maneja datos contables de varias empresas y tiene reglas que no pueden fallar: aislamiento entre empresas ([ADR-0005](0005-aislamiento-multi-tenant.md)), bloqueo de documentos enviados ([ADR-0011](0011-bloqueo-documentos-enviados.md)), importes exactos e idempotencia de la ingesta. Además, cada merge a `main` publica una versión ([ADR-0016](0016-versionado-automatico.md)), así que lo que llega a `main` debe estar probado.

## Decisión

- Todo el código de producción se desarrolla con **TDD, test primero**, en ciclos cortos:
  1. **Rojo:** escribir un test que describe el comportamiento esperado y ejecutarlo para comprobar que falla por el motivo correcto.
  2. **Verde:** escribir el código mínimo que lo hace pasar.
  3. **Refactorizar:** mejorar el código con todos los tests en verde.
- **Herramientas:** Pest (o PHPUnit) en `apps/web`, pytest en `apps/agent`, Vitest para la lógica de los componentes Vue y Playwright para los flujos E2E.
- **Niveles:** test unitario para reglas de dominio y cálculos; test de integración (base de datos real en contenedor, con RLS) para persistencia, permisos y aislamiento; test de contrato entre Laravel y FastAPI ([ADR-0015](0015-python-extrae-laravel-persiste.md)); E2E para los flujos principales.
- **Servicios externos** (Google Drive, LLM, OCR, reranker, embeddings) se sustituyen por dobles en los tests; nunca se llama a servicios reales en CI.
- **Corrección de errores:** primero un test que reproduce el fallo; después la corrección.
- **Excepciones:** configuración, infraestructura y prototipos desechables pueden no seguir el ciclo, pero el código que llegue a `main` tiene sus tests.
- **CI:** los tests, el análisis estático y la cobertura se ejecutan en cada PR; un PR con tests en rojo no se puede fusionar. La cobertura se usa como indicador, no como objetivo: el mínimo inicial es del 80 % en servicios de dominio, ingesta y RAG.

## Alternativas consideradas

- **Tests después del código:** tiende a dejar casos sin cubrir y a escribir tests que confirman lo que el código ya hace, no lo que debería hacer.
- **Solo tests E2E:** lentos y poco precisos para localizar fallos.

## Consecuencias

- Las tareas se dividen en comportamientos pequeños y verificables, y los criterios de aceptación se escriben como tests.
- El desarrollo inicial es algo más lento, a cambio de menos regresiones y de poder refactorizar con seguridad.
- Los agentes de desarrollo y QA, y la skill `tdd`, aplican este ciclo y muestran la ejecución en rojo antes de implementar.
