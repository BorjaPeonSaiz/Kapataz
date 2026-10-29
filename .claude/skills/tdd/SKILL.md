---
name: tdd
description: Implementa una funcionalidad o corrige un error siguiendo TDD (test primero, rojo-verde-refactorizar) en apps/web (Pest/PHPUnit) o apps/agent (pytest). Úsala siempre que haya que escribir o cambiar código de producción.
---

# Desarrollo guiado por tests

Referencia: `docs/adr/0017-desarrollo-guiado-por-tests.md`.

## 1. Preparar

- Lee los ADR y las secciones del plan que afecten a la tarea, y el código y los tests existentes de la zona que vas a tocar. Sigue sus patrones.
- Divide la tarea en comportamientos pequeños. Escríbelos como una lista de casos, incluyendo siempre los que apliquen:
  - camino feliz y límites;
  - errores y validación;
  - permisos por rol (`admin`, `cliente`);
  - acceso cruzado entre empresas (Paco, Juan y Alberto);
  - idempotencia y reintentos (jobs e ingesta);
  - importes y redondeos.
- Muestra la lista al usuario antes de empezar si la tarea es grande.

## 2. Ciclo por cada comportamiento

1. **Rojo.** Escribe un único test para el siguiente comportamiento. Ejecútalo y comprueba que falla **por el motivo esperado** (no por un error de sintaxis o de configuración). Muestra la salida del fallo.
2. **Verde.** Escribe el código mínimo para que pase. Ejecuta ese test y después los de la zona afectada.
3. **Refactorizar.** Mejora nombres, elimina duplicación y simplifica, sin cambiar el comportamiento. Vuelve a ejecutar los tests.

No escribas código de producción sin un test en rojo que lo justifique. Si al implementar descubres un caso nuevo, añádelo a la lista y vuelve al paso 1.

## 3. Reglas de los tests

- Deterministas: sin red real (Drive, LLM, OCR, reranker y embeddings con dobles), sin depender de la hora actual ni del orden de ejecución.
- La persistencia, RLS y los triggers se prueban contra PostgreSQL real en contenedor, no contra SQLite.
- Un test comprueba un comportamiento y su nombre lo describe (`it rejects updates to a sent invoice`).
- Para corregir un error: primero el test que lo reproduce en rojo.

## 4. Terminar

- Ejecuta la suite completa de la aplicación afectada y el análisis estático (PHPStan/Larastan, o ruff y mypy). Informa del resultado real; nunca digas que los tests pasan sin haberlos ejecutado.
- Pasa la skill `cerrar-tarea`.

Si el entorno no permite ejecutar los tests, dilo explícitamente y deja escritos los tests y el código, indicando que están sin verificar.
