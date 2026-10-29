# ADR-0022: Panel de configuración de la plataforma para el `admin`

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Muchos parámetros del negocio y de la operación cambian con el tiempo: precio de la cuota, límites por cliente, modelo de IA, claves de API, datos bancarios, correo, etc. Si viven en ficheros `.env` o en el código, cada cambio exige acceder al servidor o desplegar una versión nueva. Se quiere que el `admin` pueda hacer toda la configuración necesaria desde la propia aplicación.

A la vez, hay valores que no pueden depender de la aplicación: los que se necesitan para arrancarla, o los que darían a quien controle el panel la capacidad de desactivar las protecciones del sistema.

## Decisión

- La aplicación tiene un **panel de configuración** dentro del panel de administración, accesible solo para el rol `admin` ([ADR-0006](0006-roles-admin-cliente.md)).
- La configuración se guarda en la base de datos (`platform_settings` y `tenant_settings`), **versionada**: cada cambio crea una versión con autor, fecha, motivo y valores anterior y nuevo, y se puede volver a una versión anterior.
- Las aplicaciones leen la configuración con caché, que se invalida al guardar un cambio. No hace falta reiniciar ni desplegar.
- **Secretos** (claves de API, contraseña SMTP, credenciales OAuth de Google): se guardan cifrados con el KMS, son **de solo escritura** (el panel muestra solo los últimos 4 caracteres y la fecha de cambio) y nunca aparecen en logs, trazas ni respuestas de la API.
- Los cambios críticos (claves de API, modelo y prompt del agente, precio, datos bancarios) piden **confirmar la contraseña** y validan el valor antes de guardarlo (por ejemplo, «Probar conexión» con la API de Anthropic, el SMTP o Google).
- El acceso de `admin` exige **MFA obligatorio**.
- La configuración del agente sigue las reglas de [ADR-0004](0004-agente-unico-comun.md): una versión nueva del prompt o del modelo pasa la suite de evaluación antes de activarse.

### Fuera del panel (solo en el servidor)

Se configuran en variables de entorno o en el gestor de secretos del servidor, y el panel los muestra como mucho en solo lectura:

| Valor | Motivo |
| --- | --- |
| Conexión a PostgreSQL y Redis, `APP_KEY`, clave maestra del KMS | Se necesitan para arrancar y para descifrar el resto de la configuración |
| Copias de seguridad (destino, credenciales, contraseña de cifrado, retención) | Quien controlase el panel no debe poder desactivar ni redirigir las copias ([ADR-0021](0021-copias-de-seguridad.md)) |
| `APP_VERSION`, `APP_COMMIT`, entorno | Los fija el build ([ADR-0016](0016-versionado-automatico.md)) |

## Alternativas consideradas

- **Todo en `.env`:** cada cambio de precio o de límite exige acceso al servidor y reinicio, sin historial ni auditoría.
- **Todo en el panel, incluidas copias de seguridad e infraestructura:** cómodo, pero una cuenta de `admin` comprometida podría desactivar las copias o redirigirlas.

## Consecuencias

- El `admin` gestiona el negocio sin tocar el servidor, con historial y vuelta atrás.
- El panel de administración pasa a ser un objetivo de alto valor: MFA, reautenticación, auditoría y limitación de intentos son obligatorios.
- Cada parámetro configurable necesita validación, un valor por defecto seguro y tests.
