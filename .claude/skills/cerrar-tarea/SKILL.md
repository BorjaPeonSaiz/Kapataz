---
name: cerrar-tarea
description: Cierra una tarea del proyecto comprobando tests, aislamiento y documentación, y actualiza el estado por fases y el registro de cambios del README. Úsala al terminar cualquier tarea relevante, antes de proponer un commit.
---

# Cerrar una tarea

1. **Verificación.**
   - Ejecuta los tests y el análisis estático de las partes tocadas (`apps/web` y/o `apps/agent`) si el entorno lo permite. Informa del resultado real; si algo falla, la tarea no está cerrada.
   - Si el cambio toca datos, endpoints, jobs, el agente, el RAG, Drive o MCP, pasa la skill `revisar-aislamiento`.
2. **Decisiones.** Si durante la tarea se tomó una decisión de arquitectura que no está en los ADR, créala con la skill `nuevo-adr`.
3. **Plan.** Si el comportamiento implementado difiere del plan (`docs/proyecto/plan-de-construccion.md`), actualízalo o señálalo al usuario.
4. **Documentación para clientes.** Si la tarea cambia algo visible para el cliente, actualiza o crea la guía correspondiente con la skill `documento-cliente`, o añádela como pendiente en `docs/clientes/README.md`.
5. **README.**
   - Actualiza la tabla «Estado» si cambia el estado de una fase (`Pendiente`, `En curso`, `Hecho`).
   - Si cambian la estructura del repositorio, la puesta en marcha o las convenciones, actualiza esas secciones.
   - Añade una fila al «Registro de cambios» con la fecha de hoy y una frase sobre lo hecho.
6. **Resumen para el usuario.** Qué se ha hecho, qué se ha verificado y con qué resultado, qué ha quedado pendiente y una propuesta de mensaje de commit en inglés con formato Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `chore:`…; `!` si rompe compatibilidad), indicando qué incremento de versión provocará (MAJOR, MINOR o PATCH). No hagas commit salvo que el usuario lo pida.
