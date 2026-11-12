# HANDOFF

Memoria de continuidad entre sesiones. Lo actualiza solo el hilo principal (plan maestro, §6.3). Si Engram y este archivo se contradicen, vale este archivo.

## Estado y objetivo actual

- **Bloque en curso:** 0 — Fundaciones y documentación, en la rama `bloque-00-fundaciones`, con su PR abierto contra `main`.
- **Objetivo:** que el repositorio contenga todo el conocimiento del proyecto antes de la primera línea de código.
- **Estado:** entregables escritos y alineados con las decisiones de Borja. Falta su visto bueno al PR (criterio de terminado del bloque).
- **Hecho:**
  - `CLAUDE.md` y los 10 agentes de `.claude/agents/`, copiados del plan.
  - `docs/01-especificacion.md`, generado del plan: 141 identificadores y 33 escenarios.
  - `docs/02-arquitectura.md`, con §Diseño alineada con la marca de kodigolab.es.
  - `docs/03-modelo-amenazas.md` y `docs/04-evaluacion-ia.md`.
  - ADR-001 a ADR-033 con su índice en `docs/adr/README.md`.
  - `.engram/` añadido a `.gitignore`.
- **Decisiones aprobadas por Borja el 12/11/2026** (aplicadas al plan, la especificación, la arquitectura, el modelo de amenazas y los ADR):
  1. Se bloquea la cabeza de la cadena (`billing_chain_heads`) antes que el contador.
  2. RN-F-04 se comprueba con el contador ya bloqueado.
  3. Excepción de RN-03 para importes con IVA incluido: la cuota es la diferencia.
  4. Los esquemas Pydantic de las herramientas van en `application/agent`.
  5. Clases en inglés; las herramientas del agente, en español.
  6. Tablas nuevas: `tenants.kind`, `platform_admins`, `platform_audit_events` y `submission_authorizations`.
  7. Tablas globales sin RLS en una lista cerrada, y agregados del superadministrador con `SECURITY DEFINER`.
- **Arreglos menores aprobados y aplicados:**
  - gemelos `Fake` que faltaban;
  - marcador `owasp`;
  - ADR-030 se cierra en el Bloque 6;
  - RNF-01 incluye los datos del profesional;
  - `static/` y `docs/api/` en el árbol;
  - Semgrep y gitleaks en el stack;
  - `Payment` en el glosario.
- **Diseño:** paleta y tipografía de kodigolab.es (terracota, crema y marrón; Poppins e Inter), con el botón y los enlaces en `#B04E24` para cumplir AA. Los contrastes están en §Diseño.

## Siguiente acción

Borja revisa el PR del Bloque 0, acepta las condiciones de Anthropic (ADR-029) e integra. Después, el Bloque 1 en la rama `bloque-01-esqueleto`.

## Pendiente

### Por decidir en su bloque

- **Bloque 2:** columnas de `billing_chain_heads` (enlace al último registro o copia de sus datos de encadenamiento).
- **Bloque 4 (ADR-026):** las tablas de la cola (`procrastinate`) no tienen RLS ni están en la lista cerrada de tablas globales. Hay que meterlas en la lista o limitar la prueba al esquema de la aplicación.
- **Bloque 6 (ADR-028):** límite de uso de IA para las cuentas de cortesía y de demostración.
- **Bloque 8:** vivienda alquilada en `recipient_type`, según el RDL 29/2026 (depende del asesor).
- **Bloque 12:**
  - envío a la AEAT fuera de la transacción de emisión;
  - que el espacio de demostración y las facturas anteriores a la 1.0.0 nunca lleguen a la AEAT de producción (P-07);
  - protección de las autorizaciones con copia del DNI (P-08).
- **En el bloque al que afecte cada una:**
  - 19 propuestas de seguridad abiertas (`docs/03-modelo-amenazas.md` §8; P-14 ya resuelta);
  - umbrales de evaluación sin fijar (`docs/04-evaluacion-ia.md`);
  - 13 preguntas de diseño abiertas (`docs/02-arquitectura.md`, §Diseño).

### Respuestas de asesores

No bloquean el Bloque 1; sí cierran bloques posteriores.

- **Asesor fiscal:** reglas de IVA de la facturación por fases (ADR-033, Bloque 8), aplazamiento de VERI*FACTU para el productor, importe total del registro y validación final (Bloque 12).
- **Abogado:** condiciones de uso, contrato de encargo, política de privacidad, aviso de IA y plazos de conservación (antes de producción, Bloque 10). Comprobar también la lista oficial del Marco de Privacidad.
- **Proveedores de envío VERI*FACTU:** elección del proveedor y autorización de cada cliente (Bloque 12).
- **Anthropic:** retención cero, canal de aviso de subencargados e información para la evaluación de la transferencia (antes de usar datos reales, ADR-029). Revisar a mano la lista de subencargados, que no se pudo leer automáticamente.
- Crear la cuenta de la API de Claude con el email de la empresa: no se puede cambiar después.

## Trampas del entorno

- Windows: no hay `python` en el PATH (el de `WindowsApps` es el acceso directo a la Microsoft Store). Usar `uv run --no-project --python 3.12 python …` hasta que exista el `pyproject.toml` del Bloque 1.
- `docs/consultas/` está en `.gitignore`: las consultas a profesionales son privadas y solo existen en local.
- `docs/01-especificacion.md` se genera desde §1 y §3 del plan: si cambia un RF, RN o RNF, se cambia en el plan y se regenera, o se editan los dos a la vez.
- Los diagramas Mermaid de `docs/02` y `docs/03` no se han renderizado; solo se ha revisado la sintaxis a mano.
- markdownlint avisa de MD060 en todas las tablas (estilo compacto `|---|`, el mismo del plan). No es un error.
