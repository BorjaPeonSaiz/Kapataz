# ADR-0001: Registrar las decisiones de arquitectura con ADR

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

El plan de construcción ha cambiado varias veces mientras se definía (vigilancia del Drive, tipo de Drive, roles). Si las decisiones solo viven en el plan, se pierde por qué se tomaron y qué alternativas se descartaron.

## Decisión

Cada decisión de arquitectura relevante se registra como un ADR en `docs/adr/`, numerado y con el formato de [0000-plantilla.md](0000-plantilla.md). Un ADR aceptado no se edita; si la decisión cambia, se crea uno nuevo que lo sustituye. El plan de construcción se actualiza después, citando el ADR.

## Alternativas consideradas

- **Solo el plan de construcción:** refleja el estado actual, pero no la historia ni los motivos.
- **Decisiones en issues o en el chat:** se pierden y no viajan con el código.

## Consecuencias

- Hay un paso más antes de implementar un cambio relevante.
- Cualquier persona (o IA) que se incorpore puede entender por qué el sistema es como es.
