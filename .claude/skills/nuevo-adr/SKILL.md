---
name: nuevo-adr
description: Crea un ADR (registro de decisión de arquitectura) en docs/adr a partir de la plantilla, lo añade al índice y, si sustituye a otro, marca el anterior. Úsala cuando se tome o se cambie una decisión de arquitectura, de seguridad, de datos o de producto que afecte a cómo se construye el sistema.
---

# Crear un ADR

1. **Comprueba si ya existe.** Lee `docs/adr/README.md`. Si un ADR aceptado cubre el tema, la nueva decisión lo sustituye: no se edita el antiguo salvo su línea de estado.
2. **Número y nombre.** Usa el siguiente número libre con cuatro cifras y un título corto en minúsculas con guiones: `docs/adr/NNNN-titulo-corto.md`.
3. **Contenido.** Copia la estructura de `docs/adr/0000-plantilla.md`:
   - **Estado:** `Propuesta`, salvo que el usuario haya confirmado la decisión en la conversación; entonces `Aceptada`.
   - **Fecha:** la de hoy, en formato `AAAA-MM-DD`.
   - **Contexto:** el problema y lo que condiciona la decisión, con datos concretos.
   - **Decisión:** frases concretas y verificables (qué se hace, dónde y con qué).
   - **Alternativas consideradas:** cada una con el motivo por el que se descartó.
   - **Consecuencias:** qué se gana, qué se pierde y qué obliga a hacer.
   - Enlaza los ADR relacionados con rutas relativas.
4. **Sustitución.** Si sustituye a otro ADR, cambia solo la línea de estado del antiguo a `Sustituida por ADR-NNNN` y actualiza su estado en el índice.
5. **Índice.** Añade una fila a la tabla de `docs/adr/README.md`.
6. **Plan.** Si la decisión cambia algo del plan (`docs/proyecto/plan-de-construccion.md`), actualiza las secciones afectadas para que no se contradigan, y menciona el ADR.
7. **README.** Añade una línea al registro de cambios del `README.md` raíz.
8. **Resumen.** Indica al usuario el número del ADR, su estado y qué otros ficheros has cambiado.

Escribe en español. Si la decisión no está clara o faltan datos para tomarla, no inventes: deja el ADR como `Propuesta` y lista las preguntas abiertas en el Contexto.
