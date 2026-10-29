# ADR-0010: Archivado por carpetas y resolución manual de «Por clasificar»

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Tras analizar un documento, el agente debe guardarlo en la carpeta adecuada del Drive. Algunos documentos no son facturas, presupuestos ni documentación de proveedores, o el agente no los reconoce, y alguien tiene que decidir qué hacer con ellos.

## Decisión

- El agente determina el tipo y la dirección del documento (comparando el NIF/CIF del emisor con el de la empresa) y lo archiva:
  - Recibido de un proveedor → `Proveedores/<proveedor>/`
  - Factura emitida → `Facturas/<cliente>/`
  - Presupuesto emitido → `Presupuestos/<cliente>/`
  - Factura o presupuesto ambiguo o de baja confianza → `Revisión/`
  - Cualquier otro documento → `Por clasificar/`
- Las carpetas de cliente y proveedor se crean si no existen y se enlazan por identificador de carpeta, no por nombre.
- La sección **«Por clasificar»** lista esos documentos con un **desplegable por fila** y un botón «Aplicar»:
  - **Es factura / Es presupuesto:** el usuario elige el cliente; el agente reprocesa el documento con ese tipo forzado, lo registra y lo archiva en `Facturas/<cliente>` o `Presupuestos/<cliente>`.
  - **Es proveedor:** el usuario elige el proveedor; se archiva en `Proveedores/<proveedor>` y, si contiene una factura o presupuesto del proveedor, se registra como documento recibido.
  - **Verificado / Almacenar:** no crea registros y mueve el fichero a `Otros documentos/`.
  - **Eliminar:** con confirmación; envía el fichero a la papelera de Drive y borra la copia privada, los fragmentos y los embeddings, conservando la auditoría.
- La decisión del usuario prevalece sobre la clasificación del agente, y estos casos se guardan para la suite de evaluación.

## Alternativas consideradas

- **Dos botones (Verificar y Eliminar):** obligaba a resolver por otra vía los documentos que en realidad sí eran facturas o presupuestos.
- **Acción inmediata al cambiar el desplegable:** descartada para evitar errores por un clic accidental.

## Consecuencias

- Ningún documento queda sin carpeta: todo acaba archivado, en revisión o eliminado por decisión expresa del usuario.
- Las correcciones manuales sirven para medir y mejorar la clasificación del agente.
