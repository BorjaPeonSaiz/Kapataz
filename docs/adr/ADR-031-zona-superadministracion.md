# ADR-031 — Zona de superadministración

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-SA-01, RF-SA-02, RF-SA-03, RF-SA-04, RF-SA-05, RF-SA-06, RF-SA-07, RN-13, RF-UC-01, RN-10

## Contexto

El dueño de la plataforma necesita gestionar lo que afecta a todas las cuentas: el modelo de Claude y su `effort` por ruta (ADR-005), los límites de consumo y el tope global (ADR-028), los plazos de gracia y de solo lectura (ADR-016), las suscripciones, las cuentas de cortesía y la apertura del registro (RN-13).

Esa capacidad es peligrosa. Si un cliente la obtiene, cambia el modelo para todos o se regala acceso. Si el superadministrador puede leer facturas y clientes de las cuentas, KodigoLab trata más datos de los necesarios como encargado (RF-SA-05). Y cada cambio afecta a todos, así que debe quedar registrado (RF-SA-06).

## Opciones consideradas

1. **Indicador `is_admin` en `User`, con pantallas de administración dentro de la app.**
   - Ventajas: sencillo de construir.
   - Inconvenientes: un fallo de autorización o una asignación masiva convierte a un cliente en administrador; mezcla el rol con las cuentas de negocio.
2. **Sin zona: cambios directos en la base de datos o por línea de comandos.**
   - Ventajas: no hay superficie de ataque web.
   - Inconvenientes: sin registro de cambios ni vista de costes; errores manuales; no hay TOTP.
3. **Zona propia con rol `PlatformAdmin` aparte, TOTP obligatorio, sin acceso a datos de negocio y con todos los cambios registrados.**
   - Ventajas: el rol no se obtiene desde la app; la zona no existe para un cliente; mínimo acceso a datos.
   - Inconvenientes: más código y una forma específica de leer agregados sin leer datos de negocio.
4. **Aplicación de administración separada, en otro dominio o solo por red privada.**
   - Ventajas: aislamiento máximo.
   - Inconvenientes: otro despliegue y otro frontend que mantener para un único usuario.

## Decisión

Se elige la opción 3.

- **Rol aparte:** `PlatformAdmin` no se obtiene por registro ni por la API. Solo se crea con acceso al servidor. Los superadministradores viven en su propia tabla, `platform_admins` (§4.5 del plan).
- **TOTP obligatorio** para entrar (ADR-025).
- **La zona no existe para un cliente:** cualquier ruta de la zona responde 404 a un cliente, con sesión o sin ella. Un cliente no tiene ningún ajuste de modelo.
- **Qué gestiona:**
  - modelo de Claude y `effort` por ruta para toda la plataforma (RF-SA-02); un modelo no permitido se rechaza;
  - coste por cuenta, límite mensual por cuenta, tope global, plazos de gracia y de solo lectura (RF-SA-03);
  - suscripciones y cuentas de cortesía sin pago (RF-SA-04);
  - apertura y cierre del registro, y emails habilitados con el registro cerrado (RF-SA-07, RN-13).
- **Sin datos de negocio:** la zona solo ve metadatos y agregados (RF-SA-05). Ninguna ruta devuelve facturas, clientes ni documentos de una cuenta. Los agregados, como el coste por cuenta, salen de funciones `SECURITY DEFINER` que solo devuelven metadatos y agregados. El rol de la aplicación sigue sin `BYPASSRLS` (ADR-024).
- **Todo cambio registrado** con fecha, autor, valor anterior y valor nuevo (RF-SA-06), en `platform_audit_events`.
- **`platform_settings`** solo la escribe el superadministrador. El modelo se lee siempre de ahí, nunca del código.
- Antes de cambiar de modelo en producción, se repite la Fase 4 del plan de verificación con el modelo nuevo.
- **Sin doble uso:** ni el superadministrador puede alterar, ocultar o borrar registros de facturación.

## Consecuencias

- **Positivas:**
  - Un cliente no puede llegar a la zona ni saber que existe.
  - KodigoLab no ve datos de negocio de sus clientes.
  - Cada cambio de plataforma tiene autor, fecha y valores.
- **Negativas y mitigación:**
  - Si se pierde el segundo factor, no hay entrada desde la web. Se documenta un procedimiento de recuperación en el servidor en `docs/operacion/`.
  - Los agregados sin datos de negocio exigen funciones `SECURITY DEFINER` específicas. Se prueban para que no devuelvan columnas de negocio.
  - Un solo superadministrador es un punto único. Es aceptable para un proyecto de una persona.
- **Qué haría reconsiderarla:** varios administradores con permisos distintos, o soporte que necesite ver datos de un cliente con su consentimiento.

## Verificación

- Escenario «Zona de superadministración»: un cliente recibe 404 y no tiene ningún ajuste de modelo (`@pytest.mark.req("RF-SA-01")`).
- `test_a01_admin_404_para_clientes` (`owasp("A01")`) y prueba de que sin TOTP no se entra.
- Prueba de que ninguna ruta de la zona devuelve facturas, clientes ni documentos (`req("RF-SA-05")`).
- Prueba de que el cambio de modelo afecta a toda la plataforma, queda registrado y rechaza un modelo no permitido (`req("RF-SA-02")`, `req("RF-SA-06")`); `test_llm03_cambio_de_modelo_registrado`.
- Escenario «Registro cerrado antes de la 1.0.0» (`req("RN-13")`, `req("RF-SA-07")`).
- Prueba de que el registro y la API no permiten obtener el rol `PlatformAdmin`.
- Revisión de arquitectura: ningún nombre de modelo fijado en el código.
