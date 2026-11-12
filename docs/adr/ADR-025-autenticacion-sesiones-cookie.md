# ADR-025 — Autenticación propia con sesiones en cookie

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-AC-01, RF-AC-02, RF-AC-03, RF-AC-04, RF-SA-01, RN-13, RNF-12

## Contexto

Kapataz tiene registro abierto con email y contraseña (RF-AC-01), con la excepción del registro cerrado hasta la 1.0.0 (RN-13). El usuario abre sesión en el portátil y en el móvil, quiere ver esas sesiones y cerrarlas (RF-AC-02), recuperar la contraseña (RF-AC-03) y activar TOTP (RF-AC-04). El superadministrador tiene TOTP obligatorio (RF-SA-01).

La app y la API se sirven desde el mismo origen detrás de Caddy (ADR-013), así que no hace falta CORS. Lo que hay detrás de la sesión son datos fiscales y la capacidad de emitir facturas: una sesión robada es grave. La PWA corre en navegadores móviles, donde un token guardado en JavaScript queda expuesto a cualquier XSS.

## Opciones consideradas

1. **JWT en el navegador** (en `localStorage` o en memoria, enviado en cabecera).
   - Ventajas: sin estado en el servidor; habitual en SPA.
   - Inconvenientes: legible desde JavaScript, así que un XSS lo roba; revocar sesiones exige listas negras; RF-AC-02 pide verlas y cerrarlas.
2. **Proveedor de identidad externo** (servicio gestionado).
   - Ventajas: TOTP, recuperación y protección contra fuerza bruta resueltos.
   - Inconvenientes: otro proveedor que trata datos personales, con su transferencia y su contrato; coste por usuario; dependencia para algo que el stack resuelve bien.
3. **Autenticación propia con sesiones en servidor y cookie `HttpOnly`.**
   - Ventajas: el token no es accesible desde JavaScript; sesiones revocables y listables en `sessions`; encaja con el mismo origen.
   - Inconvenientes: hay que implementar bien la protección CSRF, la limitación de intentos, la recuperación y el TOTP.

## Decisión

Se elige la opción 3.

- Contraseñas con **Argon2id**.
- Sesión en el servidor (tabla `sessions`) con un identificador en una cookie `HttpOnly`, `Secure` y `SameSite`. Ningún token en el navegador.
- Las sesiones caducan, se pueden listar y cerrar desde cualquier dispositivo (RF-AC-02), y la sesión se renueva al iniciar sesión.
- Protección CSRF en todas las mutaciones.
- Límite de intentos con bloqueo creciente y mensajes que no revelan si un email existe.
- Verificación de email y recuperación de contraseña con enlaces de un solo uso y con caducidad, enviados por `EmailPort`.
- TOTP opcional para los clientes y obligatorio para el superadministrador (ADR-031).
- El Bloque 1 implementa registro con verificación, inicio y cierre de sesión. El Bloque 10 completa recuperación, sesiones abiertas, TOTP y cierre de cuenta.

## Consecuencias

- **Positivas:**
  - Un XSS no puede robar la sesión.
  - Cerrar una sesión robada es inmediato.
  - Ningún proveedor más que trate datos personales.
- **Negativas y mitigación:**
  - Implementar autenticación es delicado. Se mitiga usando librerías probadas para Argon2id y TOTP, sin criptografía casera, y con las pruebas A07 y A04.
  - Las cookies exigen CSRF. Se mitiga con protección en cada mutación y `SameSite`.
  - Una consulta a `sessions` por petición. Es una búsqueda por clave primaria.
- **Qué haría reconsiderarla:** una app nativa o clientes de terceros que necesiten tokens, o la necesidad de inicio de sesión federado (gestorías, equipos).

## Verificación

- `test_a07_bloqueo_creciente`, `test_a07_sin_enumeracion`, `test_a07_cookie_flags`, `test_a07_enlace_un_solo_uso` y `test_a07_sesion_revocada` (`@pytest.mark.req("RF-AC-02")` y los RF-AC que correspondan, `owasp("A07")`).
- `test_a04_password_argon2id` (`owasp("A04")`).
- Prueba de CSRF: una mutación sin el token CSRF se rechaza.
- Pruebas de cuentas del plan de verificación: email ya usado, email sin verificar, enlace caducado, contraseña débil, cierre remoto, caducidad, recuperación y TOTP.
- Prueba de superadministración: sin TOTP no se entra (`req("RF-SA-01")`).
