# ADR-0021: Copias de seguridad con pgBackRest en el VPS y Backblaze B2 gratuito

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

La base de datos contiene la contabilidad de todas las empresas y es lo único que no se puede reconstruir. Los documentos originales están además en el Google Drive de cada cliente ([ADR-0007](0007-google-drive-por-empresa.md)). Al principio se quiere un coste de 0 €, pero con la posibilidad de pasar a un almacenamiento de pago sin rehacer nada cuando crezca el volumen.

Una copia solo en el VPS protege de errores humanos y corrupción de datos, pero no de la pérdida del servidor, un incidente del proveedor, la suspensión de la cuenta o un ataque con acceso al servidor.

## Decisión

### Herramienta y destinos

- **pgBackRest** gestiona las copias de PostgreSQL con dos repositorios:
  - **`repo1`, local en el VPS** (en un volumen o directorio separado de los datos): restauración rápida ante errores.
  - **`repo2`, externo en Backblaze B2, plan gratuito, región UE**: protección ante la pérdida del VPS.
- `repo2` se configura como **almacenamiento S3 genérico**, con endpoint, región, bucket y credenciales en variables de entorno. Cambiar a un almacenamiento de pago (B2 de pago, Hetzner Object Storage, Wasabi, AWS S3, etc.) es **solo un cambio de configuración**. Añadir un tercer destino (`repo3`) también lo es.

### Frecuencia y retención

| | `repo1` (VPS) | `repo2` (B2) |
| --- | --- | --- |
| Copia completa | Semanal | Semanal |
| Copia diferencial | Diaria | Diaria |
| Registro de cambios (WAL) continuo | Sí | Sí |
| Restaurar a cualquier momento de los últimos | 14 días | 30 días |
| Copias completas que se conservan | 2 | 4 |

- **Pérdida máxima de datos:** menos de 5 minutos (`archive_timeout`). **Tiempo máximo de recuperación:** menos de 4 horas.
- Las copias mensuales de larga duración (12 meses) se añadirán al pasar a almacenamiento de pago, para no superar los 10 GB gratuitos.

### Protección de las copias

- **Cifrado** en pgBackRest (AES-256) en los dos repositorios. La contraseña de cifrado se guarda en el gestor de secretos del servidor **y fuera del VPS** (gestor de contraseñas del `admin`): sin ella, las copias no sirven.
- **Inmutabilidad en B2:** bloqueo de objetos (*object lock*) de 30 días en el bucket. La retención de pgBackRest en `repo2` es igual o mayor que el bloqueo, para que la limpieza automática solo borre copias ya desbloqueadas.
- **Credenciales de B2 con permisos mínimos:** solo sobre ese bucket, sin permiso para cambiar el bloqueo ni borrar el bucket.
- **Secretos críticos** (contraseña de pgBackRest, claves de cifrado de los tokens de Google, credenciales de B2 y `.env` de producción) con una copia cifrada fuera del VPS, en el gestor de contraseñas del `admin`.

### Comprobación

- **Cada semana**, un trabajo programado restaura la última copia de `repo2` en un contenedor temporal y comprueba que PostgreSQL arranca, que el número de filas de las tablas principales cuadra y que las huellas (`content_hash`) de las facturas enviadas coinciden. Si falla, salta una alerta.
- **Cada trimestre**, un simulacro completo de recuperación, cronometrado y documentado en `docs/proyecto/`.
- **Alertas** si una copia o el archivado del WAL fallan, o si `repo2` supera los **8 GB** (aviso para pasar a almacenamiento de pago antes de llegar a los 10 GB).

### Resto de datos

| Dato | Copia |
| --- | --- |
| Copias privadas de documentos (S3 en el VPS) | Sin copia externa por ahora: los originales están en el Drive de cada cliente y se pueden volver a descargar y reprocesar. Se incluirán en el almacenamiento externo cuando sea de pago |
| Redis (colas y caché) | Sin copia: es temporal y los trabajos son idempotentes |
| Langfuse y logs | Sin copia externa; su pérdida no afecta a los datos de negocio |

## Alternativas consideradas

- **Solo en el VPS:** no protege de la pérdida del servidor ni de un ataque.
- **Google Drive gratuito con rclone:** sin contrato de encargado de tratamiento en cuentas personales, sin inmutabilidad, cuota compartida con Gmail y sin soporte nativo en pgBackRest.
- **PC o NAS propio:** gratuito y a salvo de un atacante en el VPS, pero depende de un equipo encendido; queda como segundo destino opcional.
- **Almacenamiento de pago desde el inicio:** innecesario mientras la base de datos quepa en el plan gratuito.

## Consecuencias

- Coste de 0 € mientras `repo2` quepa en 10 GB; después, unos pocos euros al mes sin cambiar la arquitectura.
- Hay que revisar las condiciones del plan gratuito de B2 (cuota de almacenamiento, descargas y región) al contratar y cuando cambien.
- Si se pierde el VPS, se recupera la base de datos completa desde B2; las copias privadas de documentos se reconstruyen desde el Drive de los clientes.
- La política de privacidad debe indicar que los datos borrados a petición del cliente desaparecen de las copias cuando caduca su retención (30 días en B2).
