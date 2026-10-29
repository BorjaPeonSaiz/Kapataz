# ADR-0007: Google Drive propio de cada empresa con OAuth `drive.file`

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Cada empresa quiere tener sus documentos ordenados en su propio Google Drive. El equipo de la plataforma no debe ver ni gestionar usuarios ni contraseñas de Google de sus clientes.

## Decisión

- El usuario de la empresa conecta **su propio Google Drive** en el asistente de alta mediante **OAuth 2.0 de Google**. La contraseña se introduce en Google, nunca en la plataforma.
- Se solicita solo el permiso **`drive.file`**, que da acceso únicamente a los ficheros y carpetas que crea la propia aplicación.
- La plataforma crea en ese Drive la carpeta raíz de la empresa con la estructura `Entrada`, `Proveedores`, `Facturas`, `Presupuestos`, `Revisión`, `Por clasificar` y `Otros documentos`.
- El `refresh_token` se cifra con una clave por empresa en un KMS (cifrado de sobre) y solo lo descifra el servicio `drive-sync`, en memoria. No aparece en el panel del `admin`, en logs, en trazas ni en la API.
- El cliente puede desconectar el Drive desde ajustes o desde su cuenta de Google. Si el token deja de ser válido, «Subir archivos» se desactiva y se avisa al usuario.

## Alternativas consideradas

- **Unidad compartida propiedad de la plataforma, con cuenta de servicio:** evita la verificación de Google, pero los documentos no estarían en el Drive del cliente y la plataforma gestionaría su acceso.
- **Permiso completo `drive`:** permitiría detectar ficheros añadidos directamente al Drive, pero es un permiso restringido que exige la evaluación de seguridad anual de Google (CASA) y daría acceso a todo el Drive del cliente. Ver [ADR-0008](0008-entrada-solo-desde-la-aplicacion.md).

## Consecuencias

- Solo hace falta la verificación estándar de la pantalla de consentimiento OAuth (marca, dominio y política de privacidad).
- La plataforma no puede ver el resto del Drive del cliente: es una garantía técnica, no solo una política.
- Se recomienda al cliente conectar una cuenta de Google de la empresa y no la personal de un empleado.
