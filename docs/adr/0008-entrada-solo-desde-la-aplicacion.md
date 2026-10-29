# ADR-0008: Los documentos solo entran por «Subir archivos»

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Se valoró que el agente procesara también los ficheros que el cliente añade directamente en Google Drive. Las opciones estudiadas fueron una consulta de cambios cada 15 minutos (`changes.list`), una revisión diaria a las 23:00 con recuperación de días fallidos y notificaciones en tiempo real (`changes.watch`). Todas requieren el permiso restringido `drive`, con la evaluación de seguridad anual de Google, y acceso a todo el Drive del cliente.

## Decisión

- La **única vía de entrada** de documentos es la sección **«Subir archivos»** del menú principal (o adjuntar un fichero al crear una factura o presupuesto).
- Al subir: se valida tipo, tamaño y hash; se avisa si el fichero ya existe; se guarda una copia privada; se sube a `Entrada` en el Drive de la empresa y se lanza la ingesta en el momento.
- **No hay vigilancia del Drive**: ni consultas periódicas, ni revisión diaria, ni notificaciones. Los ficheros añadidos directamente en Drive no se procesan, y la aplicación lo indica en «Subir archivos».
- Los fallos se reintentan automáticamente con espera exponencial (3 intentos), una tarea programada vuelve a encolar los documentos atascados y los que agotan los intentos quedan en `failed` con un botón «Reintentar».

## Alternativas consideradas

- **Consulta de cambios cada 15 minutos y revisión diaria a las 23:00:** rechazada por ahora por el coste y el plazo de la verificación de Google, y por el acceso a todo el Drive del cliente.
- **Notificaciones en tiempo real:** mismo problema de permisos, más un webhook público y canales que caducan.

## Consecuencias

- Arquitectura más simple: sin scheduler de Drive, sin tablas de ejecuciones y sin webhook público.
- Hay que comunicar bien al cliente que «Subir archivos» es la única vía.
- Si se retoma la detección de subidas directas, hará falta un ADR nuevo que sustituya a este, el permiso `drive` y la evaluación CASA.
