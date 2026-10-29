# ADR-0011: Facturas y presupuestos bloqueados tras el envío

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Una factura o un presupuesto enviado al cliente no debe poder cambiar después, ni por error del usuario, ni por el agente, ni por un fallo del código. Las facturas tienen además obligaciones legales de conservación y corrección.

## Decisión

- Las facturas y presupuestos emitidos solo se editan en estado `draft`.
- El paso a `sent` es una acción explícita con confirmación («Marcar como enviado» en el MVP), que valida campos y totales, asigna el número definitivo y guarda `sent_at`, `sent_by` y el hash del contenido.
- Después del envío solo cambian el estado (pagada, vencida, aceptada, rechazada, caducada), las notas internas y los adjuntos internos.
- **Correcciones:** una factura enviada se corrige con una **factura rectificativa** enlazada; un presupuesto enviado, con una **nueva versión**.
- **Doble barrera:** los servicios de dominio rechazan la modificación por cualquier canal (web, API, agente, ingesta, MCP) y un trigger de PostgreSQL impide actualizar o borrar cabecera y líneas con `sent_at` informado.
- Las facturas y presupuestos recibidos de proveedores se bloquean igual cuando el usuario confirma sus datos en la revisión.

## Alternativas consideradas

- **Bloqueo solo en la aplicación:** un fallo en el código podría alterar documentos enviados.
- **Permitir editar y versionar en silencio:** incompatible con la trazabilidad exigible a una factura.

## Consecuencias

- El envío por email desde el SaaS y VeriFactu quedan como evolución; su incorporación requerirá un ADR propio.
- Hay tests del bloqueo por cada canal.
