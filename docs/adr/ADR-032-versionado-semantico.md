# ADR-032 — Versionado semántico desde la 1.0.0

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-VF-06, RF-MO-04, RN-13, RN-F-07

## Contexto

Kapataz es un sistema informático de facturación. Cada versión del sistema tiene su declaración responsable, aunque el cambio sea pequeño, con el identificador completo de la versión (RF-VF-06, art. 15 de la Orden HAC/1177/2024). El productor conserva las de todas las versiones (art. 13.3 del RD 1007/2023). Además, cada registro de facturación guarda la versión del sistema que lo generó (`system_version`, RN-F-07).

Durante la construcción (Bloques 0 a 12) no hay clientes reales: el registro está cerrado y solo se emiten facturas de demostración (RN-13). Numerar versiones en esa etapa no aporta nada y obligaría a declaraciones para un software que nadie usa.

Después de la release, el usuario necesita saber qué versión usa y cuándo hay una nueva (RF-MO-04), y KodigoLab necesita saber qué cambió en cada una.

## Opciones consideradas

1. **Sin versiones: despliegue continuo identificado por commit.**
   - Ventajas: cero ceremonia.
   - Inconvenientes: incompatible con la declaración responsable por versión; el usuario no sabe qué cambia.
2. **Versionado semántico desde el principio (0.x durante la construcción).**
   - Ventajas: hábito desde el primer día.
   - Inconvenientes: versiones sin usuarios ni declaración; ruido en el historial; tentación de publicar antes de la verificación.
3. **Versionado por calendario** (año y mes).
   - Ventajas: dice cuándo se publicó.
   - Inconvenientes: no dice si el cambio es compatible; varias versiones en un mes complican el esquema.
4. **Sin versiones durante la construcción y versionado semántico desde la 1.0.0.**
   - Ventajas: la primera versión es la primera fiable; cada versión posterior tiene significado, changelog y declaración.
   - Inconvenientes: hay que exigirlo en CI para que no se olvide.

## Decisión

Se elige la opción 4.

- **Antes de la 1.0.0:** no se publican versiones. El código se identifica por commit. En los registros de facturación, `system_version` guarda el identificador del commit.
- **La 1.0.0** es la primera versión que supera toda la Parte II (`docs/plan-verificacion-kapataz.md`), sobre una candidata congelada `1.0.0-rc.N` en la rama `release/1.0`.
- **Desde la 1.0.0**, cada cambio que modifica la app lleva versión propia al integrarse en `main`:
  - PATCH: corrección sin funciones nuevas (1.0.0 → 1.0.1);
  - MINOR: función nueva compatible (1.0.1 → 1.1.0);
  - MAJOR: cambio incompatible para los usuarios o para los datos (1.1.0 → 2.0.0).
- **Sin versión:** los cambios que no alteran lo desplegado, como documentación o CI.
- **Cada versión lleva:** número en `VERSION` (fuente única), entrada en `CHANGELOG.md`, etiqueta `vX.Y.Z`, imagen con esa etiqueta, release en GitHub, SBOM (ADR-022) y su declaración responsable (RF-VF-06).
- **Número visible** en la app, en `/api/health` y en el aviso de nueva versión de la PWA (ADR-027).
- **Verificación por versión:** todo PR pasa el flujo de §7. La Parte II completa se repite antes de cada MAJOR; en una MINOR, solo las fases afectadas.

## Consecuencias

- **Positivas:**
  - Cada versión publicada tiene su declaración responsable, como exige la normativa.
  - El usuario y el soporte saben qué versión corre y qué cambió.
  - La 1.0.0 significa algo: ha pasado la verificación completa.
- **Negativas y mitigación:**
  - Cada cambio de la app exige subir versión, changelog y declaración. Se mitiga generando la declaración en cada release (Bloque 12) y comprobándolo en CI.
  - Decidir entre MINOR y MAJOR no siempre es obvio, y una MAJOR obliga a repetir la Parte II. Se justifica en el PR y se revisa con él.
- **Qué haría reconsiderarla:** un cambio normativo que deje de exigir declaración por versión, o una cadencia de cambios que haga inviable una declaración por cada uno.

## Verificación

- Check de CI: un PR que cambia la app sin subir `VERSION` ni actualizar `CHANGELOG.md` falla.
- Prueba de `/api/health`: devuelve el número de `VERSION` (antes de la 1.0.0, el commit).
- Prueba de que `system_version` del `BillingRecord` coincide con la versión desplegada (`@pytest.mark.req("RN-F-07")`).
- Prueba de la PWA: el aviso de nueva versión muestra el número (`req("RF-MO-04")`).
- Fase 0 y Fase 13 del plan de verificación antes de etiquetar la 1.0.0.
