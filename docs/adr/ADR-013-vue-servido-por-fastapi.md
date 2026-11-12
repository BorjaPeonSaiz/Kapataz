# ADR-013 — Vue 3 servido por FastAPI detrás de un proxy TLS

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-MO-01, RF-MO-02, RF-MO-04, RF-AC-02, RNF-02, RNF-04, RNF-12

## Contexto

El frontend es una SPA con Vue 3, Vite, TypeScript, Tailwind CSS, Pinia y Vue Router: es ruta de aprendizaje y escaparate fullstack. Se usa en el navegador del portátil y como PWA en el móvil (RF-MO-01, ADR-027).

Fuerzas:

- La sesión va en una cookie `HttpOnly`, sin tokens en el navegador (ADR-025). Con app y API en el mismo origen, la cookie y la protección CSRF son sencillas y no hace falta CORS.
- El chat usa SSE (RNF-04).
- Solo HTTPS con HSTS (RNF-12); TLS lo termina Caddy (ADR-014).
- Del alta al primer uso en menos de 5 min, sin instalar nada (RNF-02).
- El cliente de API se genera desde el contrato OpenAPI (ADR-002).

## Opciones consideradas

1. **FastAPI sirve el build estático de Vue, detrás de Caddy: mismo origen para app y API**
   - Ventajas: sin CORS; cookies `SameSite` simples; una sola imagen y un solo despliegue, con app y API siempre de la misma versión.
   - Inconvenientes: Python sirve ficheros estáticos, algo menos eficiente que un servidor web; el build de Vue entra en la imagen del backend.
2. **Orígenes separados** (frontend en un dominio o CDN y API en otro)
   - Ventajas: caché de CDN; despliegues independientes.
   - Inconvenientes: CORS y cookies entre sitios; dos despliegues que pueden desincronizarse con el contrato.
3. **Caddy sirve los estáticos y hace de proxy de `/api`**
   - Ventajas: también mismo origen; servidor web eficiente para estáticos.
   - Inconvenientes: dos artefactos que versionar juntos; el build hay que copiarlo a la imagen o al volumen de Caddy.
4. **Renderizado en servidor (Nuxt)**
   - Ventajas: primera carga más rápida y SEO.
   - Inconvenientes: un servidor Node más en producción; una app privada no necesita SEO.

## Decisión

Opción 1.

- El build de Vite se copia a `backend/src/kapataz/static` al construir la imagen.
- FastAPI sirve la app en `/` y responde `index.html` a las rutas de la SPA. La API vive bajo `/api` y sus errores siguen RFC 9457.
- Caddy termina TLS, añade HSTS y hace de proxy hacia FastAPI (ADR-014).
- Los ficheros con hash del build se sirven con caché larga; `index.html` y el service worker, sin caché, para que la PWA detecte la nueva versión (RF-MO-04).
- El service worker nunca guarda respuestas de la API con datos del usuario (ADR-027).

## Consecuencias

- **Positivas**
  - Seguridad de sesión más simple: sin CORS ni cookies entre sitios.
  - App y API se despliegan y vuelven atrás juntas.
- **Negativas y mitigación**
  - Estáticos servidos por Python → caché larga para los ficheros con hash y compresión en Caddy. Si hiciera falta, se pasa a la opción 3 sin cambiar de origen.
  - CI construye el frontend antes de la imagen → etapa «build frontend» antes de «imagen» (§6.4, `plataforma-entrega`).
- **Qué haría reconsiderarla**
  - Que servir estáticos desde FastAPI afecte a RNF-04 o RNF-16.
  - Una app nativa en tiendas que consuma la API desde otro origen (§1.4).

## Verificación

- **E2E con Playwright** contra la app servida por FastAPI con `FakeLlm`, en escritorio y con emulación de móvil. `req("RF-MO-02")` en el equivalente de Playwright.
- `tests/e2e_api/test_spa.py`: una ruta de la SPA devuelve `index.html`, el manifiesto de la PWA se sirve en el mismo origen y una ruta inexistente bajo `/api` devuelve 404 como `application/problem+json`, no `index.html`. `@pytest.mark.req("RF-MO-01")`.
- `tests/e2e_api/test_sin_cors.py`: las respuestas de la API no llevan cabeceras `Access-Control-Allow-Origin`. `@pytest.mark.req("RNF-12")`.
- **CI:** la imagen contiene el build y el job de E2E la arranca antes de ejecutar Playwright.
