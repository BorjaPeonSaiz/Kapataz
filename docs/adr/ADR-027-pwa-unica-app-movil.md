# ADR-027 — PWA como única app móvil

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-MO-01, RF-MO-02, RF-MO-03, RF-MO-04, RNF-02, RNF-09, RF-VO-01, RF-PR-08, RF-FA-13

## Contexto

El autónomo usa Kapataz en el portátil por la noche y en el móvil en la obra o en casa del cliente (HU-01). Todas las funciones deben estar en el móvil, incluidas la voz y la importación de PDF (RF-MO-02), en Android y en iOS (RF-MO-01). Del alta al primer uso deben pasar menos de 5 minutos sin instalar nada (RNF-02).

En la obra la cobertura falla. Una factura que parece guardada y no lo está es peor que un aviso de «sin conexión» (HU-18). Las escrituras tienen consecuencias fiscales: numeración sin huecos (RN-F-01), fecha de expedición (RN-F-04) y registro encadenado (RN-F-07). Hay un solo desarrollador.

## Opciones consideradas

1. **Apps nativas (Android e iOS).**
   - Ventajas: acceso completo al dispositivo y presencia en tiendas.
   - Inconvenientes: tres bases de código; revisión de tiendas y su comisión; incumple RNF-02 (hay que instalar).
2. **App híbrida empaquetada** a partir del mismo frontend.
   - Ventajas: un código y presencia en tiendas.
   - Inconvenientes: publicación y mantenimiento en dos tiendas; sigue exigiendo instalar.
3. **PWA con escrituras sin conexión encoladas y sincronizadas después.**
   - Ventajas: se puede trabajar sin red.
   - Inconvenientes: conflictos de sincronización; una factura emitida sin conexión no tiene número ni registro hasta volver la red; datos del usuario guardados en el dispositivo.
4. **PWA instalable que abre sin conexión, lo avisa y no permite ni encola escrituras.**
   - Ventajas: un solo código; sin tiendas; sin conflictos; el servidor es la única fuente de verdad.
   - Inconvenientes: sin red no se puede trabajar; limitaciones de iOS con las PWA.

## Decisión

Se elige la opción 4.

- PWA instalable con `vite-plugin-pwa`: manifiesto, service worker e instalación en Android y en iOS.
- Sin conexión, la PWA abre y muestra el aviso «sin conexión». No permite ni encola escrituras (RF-MO-03).
- El service worker guarda la aplicación, nunca respuestas de la API con datos del usuario. Al cerrar sesión no quedan datos en el dispositivo.
- Cuando hay versión nueva, la PWA lo avisa sin perder lo que el usuario está escribiendo (RF-MO-04), y muestra el número de versión (ADR-032).
- Voz con MediaRecorder en Chrome, Edge y Safari.
- Compartir el PDF con el menú de compartir del sistema en el móvil y con descarga en el portátil (RF-PR-08, RF-FA-13). La app no envía nada al cliente por su cuenta.
- Diseño pensado primero para el móvil: desde 360 px y objetivos táctiles de al menos 44 px (RNF-09).
- El frontend no depende de nada que impida empaquetarlo después como app nativa (§1.4).

## Consecuencias

- **Positivas:**
  - Un solo código para portátil y móvil.
  - Sin tiendas ni comisiones; las actualizaciones llegan al momento.
  - Ninguna factura se emite sin servidor, así que la numeración y la cadena no se rompen.
- **Negativas y mitigación:**
  - Sin red no se trabaja. Se mitiga con un aviso claro, para que el usuario nunca dé por guardado algo que no lo está (HU-18).
  - iOS limita algunas funciones de las PWA. Se prueba en móviles reales: en el Bloque 1, la voz en Android e iOS en el Bloque 9 y la PWA instalada en un Android y un iPhone en el Bloque 10.
- **Qué haría reconsiderarla:** que los usuarios necesiten de verdad trabajar sin conexión, o una función del dispositivo que el navegador no ofrezca.

## Verificación

- Escenario «Sin conexión en el móvil» con `setOffline` de Playwright sobre la app ya cargada: la PWA abre, avisa y no permite emitir (`@pytest.mark.req("RF-MO-03")` o su equivalente en Playwright).
- Prueba de que el service worker no guarda respuestas de la API y de que al cerrar sesión no quedan datos (`req("RF-MO-03")`).
- Prueba de actualización: la versión nueva se avisa sin perder lo escrito (`req("RF-MO-04")`).
- Escenario «Compartir un presupuesto desde el móvil» (`req("RF-PR-08")`).
- E2E en Chromium, WebKit y emulación de móvil; instalación probada en un Android y un iPhone reales (criterio de terminado del Bloque 10).
- axe-core y comprobación de objetivos táctiles (RNF-09).
