# ADR-0009: Copia privada en S3 y PostgreSQL como fuente de verdad

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Los documentos viven en el Google Drive del cliente, que puede moverlos, borrarlos o desconectar el Drive en cualquier momento. La extracción debe ser auditable y los reintentos no pueden depender de que el fichero siga en Drive.

## Decisión

- Cada fichero subido se guarda también como **copia inmutable** en un almacenamiento privado compatible con S3, cifrado y con URLs firmadas de corta duración.
- **PostgreSQL es la fuente de verdad** de los datos. Drive es el archivo ordenado visible para el cliente; no se usa como índice ni para decidir el estado de nada.
- Cada documento conserva el JSON original de la extracción, su hash, su `drive_file_id`, su estado y sus errores.
- La ingesta es idempotente por hash y `drive_file_id`: reintentar no crea facturas, presupuestos ni clientes duplicados.

## Alternativas consideradas

- **Solo Google Drive:** si el cliente borra o mueve un fichero, se pierde la trazabilidad y no se puede reprocesar.

## Consecuencias

- Los documentos se almacenan dos veces; hay que aplicar la misma retención y el mismo borrado en ambos sitios (por ejemplo, al usar «Eliminar» en «Por clasificar»).
- Si el cliente mueve o borra un fichero a mano en Drive, los datos y la copia se conservan y la ficha del documento lo indica.
