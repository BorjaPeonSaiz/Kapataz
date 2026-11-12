# ADR-015 — Logs estructurados sin datos personales

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RNF-01, RN-11, RNF-17

## Contexto

Hay que diagnosticar fallos en producción: una ingesta que falla, un agente que tarda, un envío rechazado. Pero los datos de clientes, de proveedores y del propio profesional no pueden salir del sistema ni quedar expuestos (RNF-01), y los logs se leen, se copian y se conservan con menos cuidado que la base de datos.

Fuerzas:

- Nunca contenido de documentos, NIF, nombres de clientes ni datos de contacto en los logs.
- Correlación entre petición, ejecución del agente y tarea del worker.
- Los logs los recoge Docker desde la salida estándar (ADR-014).
- Sin analítica de terceros: ni cookies de seguimiento ni datos de uso enviados fuera.

## Opciones consideradas

1. **structlog en JSON a la salida estándar**, con campos fijos y un procesador que enmascara patrones de datos personales.
   - Ventajas: logs filtrables por campo; contexto añadido una vez por petición; enmascarado centralizado como segunda defensa.
   - Inconvenientes: una dependencia más; exige disciplina para registrar identificadores y no objetos completos.
2. **`logging` de la librería estándar en texto plano**
   - Ventajas: sin dependencias.
   - Inconvenientes: difícil de filtrar y agregar; es fácil interpolar datos personales en un mensaje.
3. **Servicio externo de observabilidad o analítica de producto**
   - Ventajas: paneles y búsquedas hechos.
   - Inconvenientes: datos que salen hacia un tercero, un subencargado más y, en el caso de la analítica, cookies y consentimiento.

## Decisión

Opción 1.

- **Campos** de cada línea: `request_id`, `run_id`, `tenant_id`, `use_case` y duración.
- **Se registran identificadores** (de factura, de documento, de tarea), nunca valores de negocio.
- **Prohibido en logs:** NIF, nombres, direcciones, emails y teléfonos de clientes, proveedores o del profesional; contenido de documentos; texto enviado a Claude o recibido de él.
- **Procesador de enmascarado** con los mismos patrones de la seudonimización (NIF, IBAN, email, teléfono). Es una segunda defensa, no la primera.
- **Trazas del agente** en `agent_runs` y `agent_steps`, sin contenido de documentos (ADR-006). Los eventos de negocio van a `audit_events`, no a los logs.
- **Sin analítica de terceros** en el backend ni en el frontend.

## Consecuencias

- **Positivas**
  - Logs útiles para diagnosticar, que se pueden conservar y compartir sin exponer datos personales.
  - Menos superficie para una fuga y ningún tercero que trate datos de uso.
- **Negativas y mitigación**
  - Diagnóstico sin contenido real → se reproduce con datos sintéticos (ADR-020) y se correlaciona por `request_id` y `run_id`.
  - Un desarrollador registra un objeto entero → procesador de enmascarado, prueba de fuga en CI y revisión de `revisor-codigo` y `seguridad-ia`.
  - Las reglas también aplican a Engram y a cualquier memoria de trabajo (Anexo B).
- **Qué haría reconsiderarla**
  - Una obligación legal de registrar accesos a datos personales: iría a una tabla de auditoría, no a los logs.
  - Que el volumen de logs exija un servicio externo: solo si está en la UE y recibe logs ya libres de datos personales.

## Verificación

- `tests/security/test_logs_sin_datos_personales.py`: ejecuta ingesta, consulta al agente y emisión con datos sintéticos, captura los logs y comprueba que no contienen los NIF, nombres ni emails de esos clientes. `@pytest.mark.req("RNF-01")`.
- `tests/unit/logging/test_enmascarado.py`: el procesador enmascara un NIF, un IBAN, un email y un teléfono. `@pytest.mark.req("RNF-01")`.
- **import-linter:** `structlog` solo se configura en `kapataz.infrastructure.logging`.
- **CI:** regla propia de Semgrep que marca llamadas de log con argumentos como `tax_id`, `name` o `email`.
- **Revisión de PR:** añadir una dependencia de analítica en `package.json` o `pyproject.toml` exige un ADR nuevo.
