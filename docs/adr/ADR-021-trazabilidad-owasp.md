# ADR-021 — Trazabilidad de OWASP

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-04, RN-05, RN-10, RN-11, RNF-12, RNF-13, RNF-17 (los que citan las tablas OWASP de `docs/plan-verificacion-kapataz.md`, Fase 7)

## Contexto

Kapataz es un servicio en internet con datos fiscales de varias cuentas y un agente con herramientas. La Fase 7 del plan de verificación revisa el OWASP Top 10 de aplicaciones web (edición 2025) y el OWASP Top 10 para aplicaciones LLM (edición 2025). Cada categoría tiene un riesgo concreto, una mitigación y una o varias pruebas con nombre.

Los requisitos ya se trazan con `@pytest.mark.req("ID")` y `traceability.py --check` (§3). Pero las categorías OWASP no son requisitos de la especificación: sin un mecanismo propio, una categoría puede quedarse sin prueba sin que nadie lo note hasta la auditoría final.

## Opciones consideradas

1. **Lista de comprobación manual en el plan de verificación.**
   - Ventajas: ya existe; no requiere código.
   - Inconvenientes: solo se mira antes de la release; entre bloques se pierde cobertura sin aviso.
2. **Escáneres externos (ZAP, Semgrep) como única evidencia.**
   - Ventajas: automáticos y conocidos.
   - Inconvenientes: no cubren riesgos de diseño propios (agente que emite sin confirmar, IDOR entre cuentas, fórmulas en el CSV).
3. **Marcador `owasp` en las pruebas y comprobación automática en `traceability.py`.**
   - Ventajas: la cobertura de cada categoría es visible y la CI falla si una se queda sin prueba; reutiliza la herramienta de trazabilidad que ya existe.
   - Inconvenientes: un marcador más que mantener; el marcador prueba que existe una prueba, no que sea buena.

## Decisión

Se elige la opción 3, junto con los escáneres de la opción 2 como evidencia adicional.

- Cada categoría tiene al menos una prueba automatizada en `backend/tests/security/`, o en Playwright cuando corresponde.
- La prueba lleva `@pytest.mark.owasp("A0X")` además de su marcador de requisito. El marcador `owasp` se registra en la configuración de pytest del Bloque 1, junto a `req`, `llm` y `slow`.
- `traceability.py --check` falla si alguna categoría se queda sin prueba.
- Las pruebas de cada categoría son las que nombra la tabla de la Fase 7 (por ejemplo, `test_a01_idor_todas_las_rutas` o `test_a05_csv_formula_neutralizada`).
- Las pruebas de las categorías LLM que necesitan el modelo real llevan además el marcador `llm` y se ejecutan en la Fase 4, fuera de CI.
- `seguridad-ia` revisa y `qa-testing` automatiza.

## Consecuencias

- **Positivas:**
  - La cobertura OWASP se vigila en cada PR, no solo antes de la release.
  - Las tablas de la Fase 7 y el código quedan enlazados por nombre de prueba.
- **Negativas y mitigación:**
  - Una prueba puede existir y ser débil. Se mitiga con la revisión de `seguridad-ia` y de `revisor-codigo`.
  - Algunas categorías se cubren con una etapa de CI y no con una prueba de pytest: A03 (etapa de seguridad y job `sbom-y-auditoria`) y, en parte, A02 (ZAP baseline) y A06 (escenarios Gherkin). El plan no indica cómo las reconoce `traceability.py`. Queda abierto para que Borja lo decida: dar a esas categorías una prueba con marcador que compruebe la configuración, o una lista de excepciones con su check de CI.
  - El plan no dice de forma expresa si el marcador y `--check` cubren también LLM01 a LLM10. Los criterios de salida hablan de «ninguna categoría OWASP sin prueba». Hasta que Borja lo confirme, las pruebas LLM se escriben con sus nombres de la tabla y se recomienda marcarlas con `owasp("LLM0X")`.
- **Qué haría reconsiderarla:** una nueva edición de OWASP con otras categorías (se actualiza la lista que lee `traceability.py`), o que la trazabilidad se lleve a una herramienta externa.

## Verificación

- `traceability.py --check` en CI (desde el Bloque 1) falla si una categoría no tiene prueba o si una prueba cita una categoría inexistente.
- Prueba del propio `traceability.py`: con una suite de ejemplo sin prueba para A05, `--check` devuelve error.
- Criterio de salida de la verificación: «`traceability.py --check` en verde: ningún requisito ni categoría OWASP sin prueba».
