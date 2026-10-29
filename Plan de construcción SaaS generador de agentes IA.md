# Plan de construcción: SaaS administrativo con asistente de IA

Oct 28, 2026 · @Borja · Actualizado Oct 29, 2026

## Resumen ejecutivo

El producto será un SaaS administrativo multi-tenant para gestionar usuarios, clientes, proveedores, facturas y presupuestos. Cada empresa tendrá un espacio de trabajo aislado y podrá crear o editar sus registros manualmente. Además, cada empresa conecta su propio Google Drive al darse de alta, con su cuenta de Google y sin compartir contraseñas con la plataforma; ahí se guardan facturas, presupuestos y demás documentación. Los ficheros se suben desde la sección «Subir archivos» del menú principal, que los deja en el Drive de la empresa. Cada vez que se sube un fichero, el agente común de la plataforma lo analiza, identifica si es una factura o un presupuesto, extrae sus datos y los de las partes relacionadas, crea o propone los registros correspondientes y mueve el fichero a la carpeta que le toca: `Proveedores/<nombre proveedor>`, `Facturas/<cliente>` o `Presupuestos/<cliente>`. Solo se analizan los ficheros subidos desde la aplicación: la plataforma no vigila el Drive en busca de cambios.

> Terminología: en este documento, *tenant* o *empresa* es el cliente del SaaS; *cliente* y *proveedor* son los terceros con los que trabaja esa empresa.

Decisiones principales:

- **Aislamiento total entre empresas (requisito crítico).** Una empresa solo ve sus propios datos, aunque comparta clientes o proveedores con otra. Si Paco y Juan tienen a Alberto como cliente y Paco pide las facturas de Alberto, el agente solo devuelve las facturas que Paco emitió a Alberto, nunca las de Juan. El aislamiento se aplica en la base de datos, en el RAG, en Drive y en el agente, y no depende de lo que el modelo decida.
- **Google Drive por empresa como archivo ordenado.** Cada tenant tiene una estructura de carpetas en Google Drive. Lo que se sube desde «Subir archivos» va a la carpeta `Entrada`, lo procesa el agente en el momento y después se archiva en la carpeta del proveedor o del cliente correspondiente. Drive es el espacio de trabajo documental del cliente, no la fuente de verdad: los datos viven en PostgreSQL.
- **Solo se procesa lo que se sube desde la aplicación.** Los ficheros que el cliente añada directamente en Google Drive no se detectan ni se analizan. Así la aplicación solo necesita el permiso reducido de Google `drive.file` (acceso únicamente a los ficheros y carpetas que crea la propia aplicación), que no exige la evaluación de seguridad anual de Google. La detección de subidas directas a Drive queda como posible evolución.
- **Dos roles y un usuario por empresa.** Solo existen el rol `admin` (el equipo de la plataforma) y el rol `cliente` (la empresa). Cada empresa tiene exactamente un usuario con rol `cliente`; no hay invitaciones ni miembros adicionales.
- **Cada empresa conecta su propio Drive.** El usuario de la empresa autoriza el acceso a su Google Drive durante el alta mediante OAuth de Google. La plataforma nunca ve ni guarda usuarios ni contraseñas de Google, y nadie del equipo de la plataforma puede ver el token de acceso: se guarda cifrado y solo lo usa el servicio de Drive. El cliente puede revocar el acceso en cualquier momento.
- **Un solo agente de IA para toda la plataforma.** Su prompt, modelo, herramientas y políticas se configuran centralmente y son iguales para todos los clientes. No hay un constructor de agentes, agentes por tenant, BYOK ni configuración individual del modelo.
- **El agente consulta dos fuentes complementarias:** los datos estructurados de la base de datos (para preguntas exactas y operaciones administrativas) y el índice RAG de documentos (para consultas semánticas y citas de los ficheros).
- **La base de datos principal es relacional.** Se recomienda PostgreSQL 16 con pgvector: PostgreSQL guarda los datos transaccionales y pgvector añade búsqueda vectorial en el mismo motor. No se debe sustituir la base de datos administrativa por una base vectorial.
- **Cada tenant mantiene sus propios documentos.** Los originales viven en almacenamiento de objetos privado; los metadatos, los datos extraídos y los fragmentos se asocian al tenant.
- **La extracción es auditable.** Se conservan el fichero original, los campos detectados, el estado de procesamiento y los errores. Los posibles duplicados y los campos de baja confianza se señalan para revisión.
- **La recuperación es híbrida y con reranking.** El RAG combina búsqueda textual y vectorial y reordena los candidatos con un reranker antes de enviarlos al LLM, para mejorar la precisión de las citas en documentos muy parecidos entre sí.
- **El agente es observable.** Logs estructurados en JSON correlacionados por `trace_id` y trazas de LLM (Opik o Langfuse autoalojado en la UE) cubren la ingesta y las consultas, y sostienen la evaluación y el despliegue gradual de versiones del agente.
- **Acceso MCP como evolución.** Tras el MVP se expone un servidor MCP autenticado por usuario para consultar los datos del tenant desde clientes como Claude, Cursor o Windsurf, reutilizando los mismos servicios y permisos que la API.

El MVP incluye registro y acceso, aislamiento de empresas, CRUD administrativo, conexión de Google Drive por empresa, subida de documentos desde la aplicación con clasificación y archivado automático, extracción asistida, consultas con respuestas basadas en la base de datos y el RAG, y panel interno de administración.

## Alcance funcional

| Funcionalidad | MVP | Evolución |
| --- | --- | --- |
| Registro, login y recuperación de contraseña, con un único usuario por empresa | Sí | Varios usuarios por empresa, SSO |
| Panel de administración de la plataforma (rol `admin`): alta, suspensión y estado de las empresas | Sí | Analítica avanzada |
| CRUD de clientes | Sí | Portal de cliente |
| CRUD de proveedores | Sí | Evaluación y clasificación |
| CRUD de facturas y líneas | Sí | Conciliación bancaria, pagos |
| CRUD de presupuestos y líneas | Sí | Conversión a factura y firma |
| Edición de facturas y presupuestos solo hasta su envío; bloqueo al enviarse | Sí, con acción «Marcar como enviado» | Envío por email desde el SaaS, VeriFactu/factura electrónica |
| Facturas rectificativas y nuevas versiones de presupuesto | Sí | Abonos parciales automatizados |
| Alta y modificación manual de registros | Sí | Importación CSV |
| Carga de ficheros PDF, imágenes, documentos ofimáticos, TXT y CSV | Sí, solo desde la sección «Subir archivos» del menú principal, que los guarda en Google Drive | Correo entrante, OneDrive/Dropbox |
| Conexión del Google Drive propio de la empresa durante el alta (OAuth, permiso `drive.file`) | Sí, obligatoria para usar «Subir archivos» | Cambio de cuenta o carpeta de Drive desde ajustes con migración |
| Detección de ficheros subidos directamente a Google Drive | No | Consulta periódica de cambios y revisión diaria; requiere el permiso `drive` y la verificación de seguridad de Google |
| Carpeta y listado «Por clasificar» para documentos que no son facturas, presupuestos ni de proveedores, con un desplegable por fila: Es factura, Es presupuesto, Es proveedor, Verificado / Almacenar y Eliminar | Sí | Subcarpetas por tipo |
| Archivado automático en `Proveedores/<proveedor>`, `Facturas/<cliente>` y `Presupuestos/<cliente>` | Sí | Renombrado configurable y subcarpetas por año |
| Extracción de facturas y presupuestos por el agente común | Sí | Más tipos documentales |
| Alta automática del cliente/proveedor relacionado | Sí, con validación y control de duplicados | Reglas de deduplicación avanzadas |
| RAG con citas sobre documentos propios del tenant | Sí, con búsqueda híbrida (texto + vector) y reranking | Reranker afinado con datos propios |
| Chat administrativo con permisos y respuestas basadas en datos | Sí | Acciones de escritura confirmadas |
| Administración interna de tenants, agente común y procesamiento | Sí | Analítica avanzada |
| Logs estructurados (JSON) y trazas de LLM por ingesta y consulta | Sí | Paneles de coste y calidad por tenant |
| Servidor MCP para clientes de IA externos (Claude, Cursor, Windsurf) | No (post-MVP) | Solo lectura primero; después escrituras con confirmación |

### Entidades y flujos administrativos

- **Usuarios y roles:** solo hay dos roles.
  - **`admin`:** el equipo de la plataforma. Accede al panel interno de administración (empresas, agente común, procesamiento y métricas), no pertenece a ninguna empresa y no usa la aplicación de las empresas. No puede ver los tokens de Google ni las contraseñas de los clientes, y cualquier acceso a datos de una empresa por soporte requiere un motivo y queda auditado.
  - **`cliente`:** el usuario de una empresa. Cada empresa tiene **exactamente un usuario**, que se crea con el registro de la empresa; no hay invitaciones ni miembros adicionales. Ese usuario tiene todos los permisos sobre los datos de su empresa: CRUD, «Subir archivos», «Por clasificar», conexión del Drive y chat con el agente. Puede cambiar su email y su contraseña y cerrar sus sesiones; el `admin` puede suspender o reactivar la cuenta.
- **Clientes:** razón social/nombre, identificador fiscal, direcciones, email, teléfono y notas. Un cliente se puede crear manualmente o detectarse en una factura/presupuesto.
- **Proveedores:** los mismos datos de identificación y contacto, más condiciones comerciales opcionales. Se pueden crear manualmente o extraerse de los documentos.
- **Facturas:** número, fechas de emisión y vencimiento, moneda, emisor, cliente/receptor, subtotal, impuestos, total, estado y líneas de detalle. Se enlazan al fichero de origen y a su extracción. Se pueden editar mientras están en borrador; una vez enviadas al cliente quedan bloqueadas.
- **Presupuestos:** número, fechas, vencimiento/validez, emisor, cliente, líneas, impuestos, total, estado y fichero de origen. Igual que las facturas, solo se editan hasta su envío.
- **Líneas:** descripción, cantidad, precio unitario, descuento, tipo/importe de impuesto y total de línea. Los importes se guardan como decimales, no como flotantes.
- **Documentos:** fichero original privado, identificador del fichero en Drive, carpeta de destino, tipo detectado, hash, metadatos, estado de ingesta, resultado extraído, puntuaciones de confianza, errores y relaciones con registros administrativos.

En cada subida desde «Subir archivos», el agente clasifica el documento. Si es factura o presupuesto, extrae el documento completo y sus partes: empresa emisora, cliente/receptor y, cuando corresponda, proveedor. Busca coincidencias por identificador fiscal y después por señales secundarias; crea las entidades ausentes dentro del mismo tenant y relaciona el documento. No duplica registros si ya existe una coincidencia. El resultado pasa por validación de campos obligatorios y reglas de consistencia. Los casos ambiguos, duplicados potenciales o de baja confianza quedan marcados para revisión en el panel. El usuario también puede confirmar o corregir los datos antes de contabilizarlos como definitivos.

Una vez procesado, el fichero se archiva en Google Drive según su tipo y su dirección:

| Documento | Cómo se identifica | Carpeta de destino |
| --- | --- | --- |
| Factura o presupuesto recibido de un proveedor, y demás documentación de proveedor | El emisor no es la empresa (su NIF/CIF no coincide con el del tenant) | `Proveedores/<nombre proveedor>/` |
| Factura emitida a un cliente | La empresa es el emisor y el receptor es un cliente | `Facturas/<nombre cliente>/` |
| Presupuesto emitido a un cliente | La empresa es el emisor y el receptor es un cliente | `Presupuestos/<nombre cliente>/` |
| Factura o presupuesto ambiguo o de baja confianza | Falta el emisor o el receptor, hay conflicto de identidad o la confianza es baja | `Revisión/` hasta que el usuario lo resuelva |
| Documento que no es factura, presupuesto ni documentación de un proveedor identificado | Contratos, albaranes de clientes, fotos, documentos personales o ficheros que el agente no reconoce | `Por clasificar/` hasta que el usuario elija qué hacer con él (ver «Documentos por clasificar») |

El nombre de la carpeta usa el nombre normalizado del proveedor o cliente registrado en el SaaS. Si la carpeta no existe, el agente la crea. Si el cliente o proveedor se renombra en el SaaS, la carpeta se renombra con él, porque el enlace se guarda por identificador de carpeta y no por nombre. Cuando el usuario corrige una clasificación en el panel, el fichero se mueve a la carpeta correcta.

### Documentos por clasificar

Los ficheros que el agente no identifica como factura, presupuesto o documentación de un proveedor se mueven a la carpeta `Por clasificar/` del Drive y aparecen en la sección **«Por clasificar»** del menú principal, con un contador de pendientes.

**Listado.** Una fila por documento con: nombre del fichero, fecha de subida, tipo que sugiere el agente (por ejemplo, «contrato», «albarán», «nómina» o «desconocido»), un resumen de una línea, vista previa y enlace al fichero en Drive. Se puede filtrar por fecha y por tipo sugerido. Cada fila tiene un **desplegable de acción** con cinco opciones; según la que elija el usuario, el documento se registra y se guarda en la carpeta correspondiente:

| Opción | Qué pide al usuario | Qué hace en la aplicación | Carpeta de destino en Drive |
| --- | --- | --- | --- |
| **Es factura** | El cliente al que se emitió (el agente lo propone si lo ha detectado; se puede elegir uno existente o crearlo) | El agente vuelve a procesar el documento como factura emitida: extrae cabecera, líneas, impuestos y totales y registra la factura enlazada al cliente. Si faltan datos obligatorios o la confianza es baja, queda en revisión | `Facturas/<nombre cliente>/` |
| **Es presupuesto** | El cliente al que se emitió (propuesto por el agente, existente o nuevo) | El agente lo vuelve a procesar como presupuesto emitido y registra el presupuesto y sus líneas enlazados al cliente, con la misma validación | `Presupuestos/<nombre cliente>/` |
| **Es proveedor** | El proveedor (propuesto por el agente, existente o nuevo) | El documento se enlaza al proveedor. Si el agente encuentra en él una factura o un presupuesto del proveedor, lo registra como documento recibido; si no, queda como documentación del proveedor sin registros económicos | `Proveedores/<nombre proveedor>/` |
| **Verificado / Almacenar** | Nada | Confirma que el documento es correcto y no requiere ninguna acción administrativa. Pasa a estado `verified` y no crea clientes, proveedores, facturas ni presupuestos. Sigue disponible en la sección Documentos y en las búsquedas del agente | `Otros documentos/` |
| **Eliminar** | Confirmación | Para ficheros subidos por error. El documento pasa a estado `deleted`, sale de las búsquedas del agente y se borran su copia privada en S3, sus fragmentos y sus embeddings. Solo queda el registro de auditoría (cuándo y nombre del fichero) | Se envía a la papelera de Google Drive, donde Google lo conserva 30 días por si hay que recuperarlo |

- **Aplicación de la opción.** La acción se ejecuta al confirmar la fila (botón «Aplicar» junto al desplegable), no al cambiar el valor, para evitar errores por un clic accidental. Al aplicarla, el documento sale del listado y se guarda quién eligió qué opción y cuándo.
- **El usuario manda sobre el agente.** Si el usuario elige «Es factura», el agente no vuelve a clasificarlo: lo procesa como factura aunque antes no lo reconociera. Estos casos se guardan para la suite de evaluación, porque indican documentos que el agente clasificó mal.
- **Acciones en bloque.** Se pueden seleccionar varias filas y aplicarles a la vez «Verificado / Almacenar» o «Eliminar», con una sola confirmación. Las opciones que piden un cliente o un proveedor se aplican fila a fila.
- **Solo afecta a «Por clasificar».** Este desplegable no se puede usar sobre facturas o presupuestos ya registrados: para eso están el CRUD y las reglas de bloqueo de documentos enviados.
- **Un documento eliminado no vuelve solo.** Si el usuario lo restaura desde la papelera de Google, la aplicación no lo detecta. Para que se procese otra vez hay que volver a subirlo desde «Subir archivos», y se analiza como un fichero nuevo.
- **Evolución.** Subcarpetas de `Otros documentos/` por tipo sugerido.

La carga nunca convierte automáticamente una respuesta generada en una operación financiera externa. El agente puede registrar los datos extraídos en el SaaS; los pagos, el envío automático de facturas por el agente y otras acciones irreversibles quedan fuera del MVP.

### Edición y bloqueo de facturas y presupuestos

Las facturas y los presupuestos emitidos por la empresa se pueden modificar manualmente hasta que se envían al cliente. A partir del envío ya no se pueden modificar.

| Estado | Factura | Presupuesto | ¿Editable? |
| --- | --- | --- | --- |
| Borrador | `draft` | `draft` | Sí: cabecera, cliente, líneas, impuestos, fechas y notas |
| Enviado | `sent` | `sent` | No |
| Posteriores | `paid`, `overdue`, `rectified` | `accepted`, `rejected`, `expired` | No; solo cambia el estado |

- **Acción de envío.** El paso de `draft` a `sent` es una acción explícita del usuario («Marcar como enviado» en el MVP; envío por email desde el SaaS más adelante), con confirmación previa. Antes de enviar se validan los campos obligatorios y los totales, se asigna el número definitivo y se guardan `sent_at`, `sent_by` y el hash del contenido enviado.
- **Qué se bloquea.** Todo el contenido del documento: número, fechas, emisor, cliente, líneas, importes, impuestos y el PDF generado. Después del envío solo pueden cambiar el estado (pagada, vencida, aceptada, rechazada, caducada), las notas internas y los adjuntos internos, y cada cambio queda en la auditoría.
- **Cómo se corrige un documento enviado.** Una factura enviada se corrige con una **factura rectificativa** enlazada a la original, que queda en estado `rectified`; no se edita ni se borra. Un presupuesto enviado se corrige creando una **nueva versión** (borrador editable) enlazada al anterior, que queda sustituido.
- **El bloqueo se aplica en el servidor y en la base de datos.** Los servicios de dominio rechazan cualquier modificación de un documento enviado, venga de la web, la API, el agente, la ingesta o MCP. Además, un trigger de PostgreSQL impide actualizar o borrar la cabecera y las líneas de facturas y presupuestos con `sent_at` informado, para que un fallo en el código tampoco pueda alterarlos.
- **El agente tampoco puede modificarlos.** Si un usuario pide al agente cambiar una factura enviada, el agente explica que está bloqueada y ofrece preparar una rectificativa (o una nueva versión del presupuesto) para que el usuario la confirme.
- **Documentos de proveedores.** Esta regla se aplica a lo que emite la empresa. Las facturas y presupuestos recibidos de proveedores no se envían: sus datos extraídos se pueden corregir hasta que el usuario los confirma en la revisión, y después quedan también bloqueados salvo el estado.

## Aislamiento entre empresas (requisito crítico)

Cada empresa cliente del SaaS es un tenant y solo puede ver sus propios datos. Esto se aplica también cuando dos empresas comparten un mismo cliente o proveedor.

**Ejemplo de referencia.** Paco y Juan son dos empresas cliente del SaaS. Las dos tienen a Alberto como cliente.

| Quién pregunta | Pregunta | Qué debe devolver | Qué nunca debe devolver |
| --- | --- | --- | --- |
| Paco | «Dame las facturas de Alberto» | Solo las facturas que Paco ha emitido a Alberto | Las facturas que Juan ha emitido a Alberto, ni siquiera su número o su importe total |
| Juan | «¿Cuánto me debe Alberto?» | La suma de las facturas pendientes de Juan a Alberto | Cualquier dato de Paco |
| Paco | «¿Alberto trabaja con otras empresas?» | Que no tiene esa información | Que Alberto también es cliente de Juan |

**Reglas que garantizan el aislamiento:**

1. **Un cliente o proveedor compartido son registros distintos.** Alberto existe dos veces en la base de datos: una fila en `customers` con el `tenant_id` de Paco y otra con el `tenant_id` de Juan. No existe una ficha global de clientes ni de proveedores. La deduplicación por NIF/CIF solo compara dentro del mismo tenant (restricción única `(tenant_id, tax_id)`), así que la extracción de un documento de Paco nunca puede enlazarse con el Alberto de Juan.
2. **El tenant sale de la sesión, nunca del modelo.** El `tenant_id` se obtiene del usuario autenticado en el servidor y se inyecta en cada herramienta del agente. El LLM no recibe ni elige el `tenant_id`: si la pregunta o un documento mencionan otra empresa o un identificador ajeno, la consulta sigue limitada al tenant de la sesión.
3. **Row Level Security en PostgreSQL.** Todas las tablas de negocio tienen políticas RLS por `tenant_id`, y cada conexión fija `app.tenant_id` al inicio de la transacción. Aunque un servicio olvide el filtro, la base de datos no devuelve filas de otro tenant. Las claves foráneas compuestas `(tenant_id, id)` impiden enlazar una factura de Paco con un cliente de Juan.
4. **RAG filtrado por tenant antes de buscar.** La búsqueda vectorial y textual filtra por `tenant_id` dentro de la propia consulta, no después. El reranker y el LLM solo reciben fragmentos del tenant de la sesión.
5. **Drive separado.** Cada empresa usa su propio Google Drive, conectado con su propia cuenta, y el token de una empresa solo se usa en trabajos de esa empresa. La carpeta `Facturas/Alberto` de Paco y la de Juan son carpetas distintas en espacios distintos; un fichero subido por Paco nunca se archiva en el Drive de Juan.
6. **Contexto del agente separado.** Conversaciones, memoria, cachés (claves con prefijo de tenant), colas y trazas se guardan por tenant. El agente nunca reutiliza el contexto de una conversación de otra empresa.
7. **Respuestas sin pistas.** Si un registro no pertenece al tenant, el resultado es «no encontrado», igual que si no existiera. El agente no confirma ni sugiere la existencia de datos de otras empresas.
8. **Administradores de plataforma.** El acceso interno a datos de un tenant (soporte) requiere un motivo, queda auditado y no se hace a través del agente.

**Pruebas obligatorias.** La suite automatizada incluye este escenario: dos tenants (Paco y Juan) con el mismo cliente (Alberto, mismo NIF) y facturas en ambos. Se comprueba que Paco solo obtiene sus facturas por API, CRUD, búsqueda, chat del agente, RAG, Drive y MCP. También se prueban intentos explícitos de saltarse el aislamiento: pedir «las facturas de Alberto de Juan», usar identificadores de otro tenant y subir documentos con instrucciones ocultas para el agente. Un fallo en estas pruebas bloquea el despliegue.

## Recomendación de base de datos: relacional más vectorial

Una base vectorial **no** es la alternativa adecuada para usuarios, clientes, proveedores, facturas o presupuestos: estas entidades necesitan claves, restricciones, relaciones, transacciones, filtros y sumas exactas. Esa es la función de una base de datos relacional.

Para este producto se recomienda **PostgreSQL 16 con pgvector**:

1. PostgreSQL será la fuente de verdad para cuentas, permisos, clientes, proveedores, documentos, facturas, presupuestos, líneas y auditoría.
2. `pgvector` almacenará embeddings de fragmentos para recuperar texto semánticamente. Puede convivir con los datos relacionales en PostgreSQL.
3. Las preguntas como «¿cuánto suman las facturas vencidas?» se resuelven con consultas tipadas y agregaciones SQL, nunca aproximando con similitud vectorial.
4. Las preguntas sobre el contenido de un documento recuperan fragmentos relevantes por tenant y devuelven citas al fichero/página.
5. La búsqueda textual (`tsvector` de PostgreSQL) y la vectorial se combinan (por ejemplo con Reciprocal Rank Fusion) y un reranker reordena los candidatos, sin cambiar el sistema transaccional.
6. Los ficheros originales se guardan en almacenamiento de objetos compatible con S3 como copia inmutable para auditoría y procesamiento, además de en Google Drive. Drive es el archivo ordenado visible para el cliente; no se usa como índice ni como fuente de verdad, y los ficheros no se guardan como vectores.

MySQL también podría ser la base relacional, pero no aporta una ventaja decisiva para este alcance y obligaría a decidir aparte dónde operar la búsqueda vectorial. PostgreSQL + pgvector permite comenzar con una arquitectura más sencilla. Si el volumen de documentos lo exige en el futuro, el índice vectorial podrá separarse sin migrar la base transaccional.

## Arquitectura

La aplicación web usa Laravel para autenticación, permisos, CRUD, API, colas y dashboard. Un servicio Python/FastAPI procesa documentos y ejecuta el agente común. PostgreSQL con pgvector es la fuente de verdad y el índice vectorial inicial; Redis gestiona trabajos asíncronos. El almacenamiento de objetos conserva los originales. Un servicio de Drive sube los ficheros al Drive de cada empresa y los archiva una vez procesados.

Flujo de carga y consulta:

1. El usuario sube uno o varios ficheros desde la sección «Subir archivos» del menú principal (o los adjunta al crear una factura o presupuesto). Es la única vía de entrada de documentos.
2. Laravel valida el tenant, el usuario, el tipo, el tamaño y el hash. Si el fichero ya se había subido (mismo hash), avisa al usuario en lugar de procesarlo de nuevo. Si es válido, guarda una copia en un bucket privado, crea un registro `documents` con estado `queued`, sube el fichero a la carpeta `Entrada` del Drive de la empresa, guarda su `drive_file_id` y encola la ingesta.
3. El worker extrae texto y estructura (incluidas tablas y líneas), clasifica el documento y detecta entidades/campos.
4. Si es factura o presupuesto, valida y normaliza los datos, detecta coincidencias, crea o relaciona cliente/proveedor según proceda y persiste factura/presupuesto y líneas dentro de una transacción.
5. El worker fragmenta el texto, genera embeddings y guarda los fragmentos vinculados al tenant y al documento.
6. El servicio de Drive mueve el fichero de `Entrada` a `Proveedores/<proveedor>`, `Facturas/<cliente>`, `Presupuestos/<cliente>`, `Revisión` o `Por clasificar`, creando la carpeta si no existe.
7. El dashboard muestra el estado, los registros creados/actualizados, la carpeta de destino y los problemas que requieren revisión.
8. El agente responde consultando el servicio de datos para hechos estructurados y el retriever RAG para evidencia documental. El retriever hace búsqueda híbrida filtrada por tenant, reordena los candidatos con un reranker y envía al LLM solo los mejores fragmentos. Las respuestas incluyen citas cuando se basan en documentos.

El agente no recibe acceso SQL arbitrario. Usa servicios y consultas permitidas, con validación de tenant y permisos en el servidor. Las respuestas del RAG son datos no confiables y no pueden cambiar las instrucciones del agente.

### Integración con Google Drive

#### Conexión del Drive durante el alta

El Drive lo configura el propio cliente al empezar a usar la aplicación, sin intervención del equipo de la plataforma:

1. Tras registrarse, el usuario de la empresa (rol `cliente`) ve el paso **«Conecta tu Google Drive»** del asistente de alta. Solo él puede conectarlo o cambiarlo; el `admin` de la plataforma no puede.
2. Al pulsar el botón, Google muestra su propia pantalla de inicio de sesión y de permisos. El usuario se identifica en Google, no en la plataforma, y acepta que la aplicación cree y gestione sus propios ficheros en su Drive.
3. Google devuelve a la plataforma un token de acceso (OAuth 2.0 con `refresh_token`), nunca la contraseña. El token es necesario para que el archivado y los reintentos, que se ejecutan en segundo plano, funcionen aunque el usuario ya no esté conectado.
4. La plataforma crea en ese Drive la carpeta raíz de la empresa (por ejemplo, `Facturación - <Empresa>`) con su estructura, y hace una prueba de escritura y lectura.
5. Se muestra la conexión como activa, con la cuenta de Google conectada visible solo para los usuarios de la empresa. Hasta completar este paso, «Subir archivos» está desactivado y se muestra un aviso para conectar el Drive.

**Recomendación al cliente:** conectar una cuenta de Google de la empresa (por ejemplo, `administracion@empresa.com`) y no la personal de un empleado, para que el acceso no se pierda si esa persona se va.

**Qué no ve la plataforma:**

- Usuarios y contraseñas de Google: nunca pasan por la plataforma.
- El resto del Drive del cliente: con el permiso `drive.file`, Google solo deja acceder a los ficheros y carpetas que ha creado la propia aplicación. La plataforma no puede ver ni leer ningún otro fichero del cliente, aunque quisiera.
- El token: se cifra con una clave por tenant gestionada en un KMS (cifrado de sobre). Solo el servicio `drive-sync` puede descifrarlo, en memoria y en el momento de usarlo. No aparece en el panel de administración interno, ni en logs, trazas, copias exportables o respuestas de la API.
- Los usuarios con rol `admin` solo ven el estado de la conexión (activa, caducada o revocada) y los errores de archivado, no el token ni el contenido del Drive.

**Revocación y caducidad.** El cliente puede desconectar el Drive desde ajustes (la plataforma revoca el token y lo borra) o directamente desde su cuenta de Google. Si el token deja de ser válido, la conexión pasa a `disconnected`, «Subir archivos» se desactiva para esa empresa, los archivados pendientes quedan en espera y el usuario de la empresa recibe un aviso para volver a conectarlo. Al reconectar, se completan los archivados pendientes.

#### Estructura de carpetas

Al conectar el Drive, la plataforma crea la estructura de carpetas de la empresa:

```text
<Empresa>/
├── Entrada/                     # destino temporal de «Subir archivos» mientras se procesa el fichero
├── Proveedores/
│   └── <Nombre proveedor>/      # todo lo recibido de ese proveedor
├── Facturas/
│   └── <Nombre cliente>/        # facturas emitidas a ese cliente
├── Presupuestos/
│   └── <Nombre cliente>/        # presupuestos emitidos a ese cliente
├── Revisión/                    # facturas y presupuestos con dudas, pendientes de validación manual
├── Por clasificar/              # documentos que no son facturas, presupuestos ni de proveedores
└── Otros documentos/            # documentos marcados como «Verificado / Almacenar» en «Por clasificar»
```

- **Permisos de Google.** La aplicación usa solo el permiso `drive.file`, que da acceso únicamente a los ficheros y carpetas que crea la propia aplicación. Google no lo considera restringido: basta con la verificación estándar de la pantalla de consentimiento OAuth (marca, dominio y política de privacidad), sin la evaluación de seguridad anual (CASA) que exige el permiso completo `drive`.
- **Solo se procesa lo subido desde la aplicación.** Los ficheros que el cliente añada directamente en Google Drive, aunque sea dentro de las carpetas de la empresa, no se detectan ni se analizan: con `drive.file` la aplicación ni siquiera puede verlos. En «Subir archivos» y en la ayuda se explica que es la única vía para que el agente procese un documento.
- **Idempotencia.** La clave es el hash del fichero, calculado antes de subirlo a Drive, junto con su `drive_file_id`. Si el usuario sube el mismo fichero dos veces, la aplicación le avisa de que ya existe y enlaza al documento original; puede forzar la subida si es intencionado, y en ese caso el documento va a `Revisión` como posible duplicado.
- **Archivado.** El fichero se mueve con `files.update` (`addParents`/`removeParents`), así conserva su identificador e historial en Drive. Las carpetas de cliente y proveedor se guardan por `drive_folder_id` asociado al registro del SaaS.
- **Coherencia.** Si el usuario corrige el tipo, el cliente o el proveedor en el panel, el fichero se mueve en Drive. Si alguien mueve o borra a mano en Drive un fichero subido por la aplicación, los datos extraídos y la copia de auditoría se conservan. Si después la aplicación necesita moverlo y ya no lo encuentra, lo indica en la ficha del documento.
- **Errores y reintentos.** Si falla la subida a Drive, la ingesta o el archivado, el trabajo se reintenta automáticamente con espera exponencial (por ejemplo, 3 intentos en total). Una tarea programada cada pocos minutos detecta documentos atascados en `queued` o `processing` más de un tiempo máximo (por ejemplo, 1 hora) y los vuelve a encolar. Si se agotan los intentos, el documento queda en `failed`, con el error visible en la sección Documentos y un botón «Reintentar»; el fichero sigue a salvo en la copia de S3.
- **Límites.** Se respetan las cuotas de la API de Drive con reintentos y espera exponencial, y una cola por tenant para que una carga masiva de un cliente no retrase a los demás.

### Observabilidad

Todos los servicios (Laravel, FastAPI y workers) emiten logs estructurados en JSON con `trace_id`, `tenant_id`, `user_id`, `document_id` y `agent_version` cuando aplican, para poder seguir una petición de extremo a extremo. Las llamadas al LLM, al modelo de embeddings y al reranker se registran como trazas en Opik (o Langfuse) autoalojado en la UE: entrada y salida resumidas, latencia, tokens, coste, versión del agente y resultado de validación. El contenido de los documentos y los datos personales se enmascaran o se omiten en trazas y logs. Las trazas alimentan la suite de evaluación, la comparación entre versiones del agente y el seguimiento del coste por tenant.

### Acceso MCP (post-MVP)

Un servidor MCP en el servicio FastAPI expone herramientas sobre los mismos servicios de dominio que usa el agente: `buscar_facturas`, `facturas_vencidas`, `resumen_cliente`, `resumen_proveedor` y `buscar_en_documentos` (RAG con citas). Cada usuario se autentica con OAuth y el servidor aplica su tenant y su rol en cada llamada; no existen claves compartidas. La primera versión es de solo lectura; las herramientas de escritura (por ejemplo `crear_presupuesto`) llegarán después con confirmación explícita y auditoría. En este canal el modelo lo aporta el cliente externo, por lo que el servidor MCP expone datos y herramientas, no la configuración del agente común.

## Stack recomendado

| Capa | Tecnología | Función |
| --- | --- | --- |
| Web y API | Laravel 12 + Inertia.js + Vue 3 + TypeScript + Tailwind CSS | SaaS, CRUD, autenticación, permisos y dashboard |
| Procesamiento y agente | Python 3.12 + FastAPI | Extracción, clasificación, embeddings y runtime compartido |
| Base de datos | PostgreSQL 16 + pgvector | Datos transaccionales y búsqueda vectorial |
| Colas y caché | Redis 7 + Laravel Horizon / worker Python | Ingesta, archivado y trabajos asíncronos con reintentos |
| Ficheros | Almacenamiento privado S3 compatible | Copia inmutable de los originales y exportaciones |
| Drive de la empresa | Google Drive API v3 + OAuth 2.0 de Google con permiso `drive.file` (cada empresa conecta su propio Drive) | Subida de ficheros y archivado por carpetas |
| Cifrado de credenciales | KMS (cifrado de sobre con clave por tenant) | Tokens de Google cifrados que solo descifra `drive-sync` |
| Tareas programadas | Laravel Scheduler (cron) | Detectar y volver a encolar documentos atascados |
| OCR/extracción | PyMuPDF/pypdf, docx, TXT/CSV, extracción tabular y OCR cuando sea necesario | Lectura de PDF, imagen, documentos y texto plano |
| LLM | Proveedor/modelo común configurado por el administrador de plataforma | Misma configuración para todos los tenants |
| Reranking | Cross-encoder local (p. ej. `bge-reranker`) o API (Cohere Rerank, Voyage) | Reordenar los candidatos de la búsqueda híbrida |
| Observabilidad LLM | Opik o Langfuse autoalojado en la UE | Trazas, coste, evaluaciones y comparación de versiones |
| Logs | Logs JSON (Monolog JSON en Laravel, structlog en Python) + Loki/Grafana o equivalente | Correlación por `trace_id` y filtrado por tenant |
| MCP (post-MVP) | SDK oficial de MCP para Python sobre FastAPI + OAuth 2.1 | Acceso a los datos del tenant desde clientes de IA externos |
| Pagos | Stripe + Laravel Cashier, si se monetiza con suscripción | Checkout y ciclo de suscripción |
| Entorno | Docker Compose + GitHub Actions | Desarrollo, pruebas y despliegue |

La configuración común del agente se guarda en ajustes de plataforma versionados y solo es editable por administradores internos. Las claves del proveedor se cifran y nunca se exponen a los tenants, al navegador ni a logs. La configuración admite cambiar el modelo centralmente sin crear agentes por cliente.

## Modelo de datos inicial

Todas las tablas de negocio llevan `tenant_id` y una política de Row Level Security. Las claves foráneas compuestas `(tenant_id, id)` impiden referencias cruzadas entre tenants, y las restricciones únicas de clientes, proveedores y números de documento incluyen siempre `tenant_id`. Un mismo cliente real compartido por dos empresas tiene un registro por empresa (ver «Aislamiento entre empresas»).

| Tabla | Campos principales | Notas |
| --- | --- | --- |
| `tenants` | id, name, tax_id, status, plan | Organización/espacio de trabajo |
| `users` | id, tenant_id, name, email, password, role (admin/cliente), status | `cliente`: `tenant_id` obligatorio y único (un solo usuario por empresa); `admin`: sin `tenant_id`, solo accede al panel interno |
| `subscriptions` | tenant_id, stripe ids, status, period dates | Opcional según modelo comercial |
| `customers` | id, tenant_id, name, tax_id, email, phone, address, drive_invoices_folder_id, drive_quotes_folder_id | Clientes y receptores; carpetas en `Facturas/` y `Presupuestos/` |
| `suppliers` | id, tenant_id, name, tax_id, email, phone, address, drive_folder_id | Proveedores y emisores; carpeta en `Proveedores/` |
| `drive_connections` | id, tenant_id, connected_by, connected_at, google_account_email, granted_scopes, root_folder_id, inbox_folder_id, review_folder_id, unclassified_folder_id, other_docs_folder_id, encrypted_refresh_token (cifrado con clave KMS del tenant, nunca expuesto), status (active/disconnected/revoked) | Una por tenant; conexión y carpetas base |
| `documents` | id, tenant_id, uploaded_by, drive_file_id, drive_folder_id, storage_key, mime, hash, type, suggested_type, summary, direction (emitido/recibido), status (queued/processing/needs_review/completed/unclassified/verified/deleted/failed), attempts, last_attempt_at, manual_action (invoice/quote/supplier/verified/deleted), manual_action_by, manual_action_at, extracted_data, confidence, error | Copia privada, ubicación en Drive y ciclo de ingesta; único por (tenant_id, drive_file_id) |
| `invoices` | id, tenant_id, document_id, customer_id, supplier_id, number, issue_date, due_date, currency, totals, status, sent_at, sent_by, content_hash, rectifies_invoice_id | Datos normalizados; únicas por reglas de negocio configurables; contenido bloqueado por trigger cuando `sent_at` está informado |
| `invoice_lines` | id, tenant_id, invoice_id, description, quantity, unit_price, tax, discount, total | Detalle de factura |
| `quotes` | id, tenant_id, document_id, customer_id, supplier_id, number, version, issue_date, valid_until, currency, totals, status, sent_at, sent_by, content_hash, replaces_quote_id | Presupuesto/oferta; bloqueado al enviarse, se corrige con una nueva versión |
| `quote_lines` | id, tenant_id, quote_id, description, quantity, unit_price, tax, discount, total | Detalle de presupuesto |
| `document_chunks` | id, tenant_id, document_id, ordinal, text, page, metadata, embedding, text_search | Índice vectorial HNSW e índice GIN sobre `tsvector`; filtro tenant obligatorio |
| `agent_settings` | version, prompt, provider, model, encrypted credentials, parameters, updated_by | Una configuración global común; solo admins de plataforma |
| `conversations` / `messages` | tenant_id, user_id, content, citations, usage, trace_id, agent_version, timestamps | Historial según retención; enlace a la traza del LLM |
| `audit_log` | tenant_id, user_id, action, target, channel (web/api/mcp), trace_id, metadata, created_at | Auditoría de cambios y actividad |
| `oauth_clients` / `oauth_tokens` | id, tenant_id, user_id, client_name, scopes, expires_at, revoked_at | Post-MVP: autorización por usuario del servidor MCP |

Los importes usan `DECIMAL`/`NUMERIC` con precisión definida y códigos ISO de moneda. Los documentos extraídos conservan el JSON original de extracción para auditoría, pero el CRUD opera sobre columnas normalizadas. `tax_id` y números de documento se normalizan antes de comparar; las reglas de unicidad admiten excepciones justificadas por tenant.

## Experiencia de usuario

### CRUD

Dashboard con navegación a clientes, proveedores, facturas, presupuestos, documentos, «Subir archivos» y «Por clasificar» (con contador de pendientes). Cada entidad tiene listado paginado con búsqueda, filtros, ordenación, ficha de detalle, creación, edición y archivado/borrado según permisos y obligaciones de auditoría. Los formularios muestran validaciones de negocio e importes calculados. Las facturas y presupuestos en borrador se editan con normalidad; al enviarlos, la ficha pasa a solo lectura, muestra la fecha y el usuario del envío y ofrece «Crear rectificativa» o «Nueva versión» en lugar de «Editar». Un registro manual y uno extraído por el agente usan los mismos servicios de dominio para mantener reglas coherentes.

### Subida y extracción asistida

El menú principal tiene una sección **«Subir archivos»**: el usuario arrastra o selecciona uno o varios ficheros, que se suben a la carpeta `Entrada` del Drive de la empresa y se procesan en el momento. También puede adjuntar un fichero al crear una factura o presupuesto, que sigue el mismo camino. Es la única vía para que el agente procese un documento; la pantalla lo indica con un texto breve («Los ficheros que añadas directamente en Google Drive no se procesan»). Los ficheros de un tipo no admitido o demasiado grandes se rechazan antes de subirlos, con el motivo. El Drive se conecta en el asistente de alta («Conecta tu Google Drive»). Después, en ajustes, el usuario ve la cuenta conectada y el estado de la conexión, y puede reconectar o desconectar el Drive. Durante el procesamiento ve estados `queued`, `processing`, `needs_review`, `completed`, `unclassified` o `failed`; los fallidos muestran el error y un botón «Reintentar». La vista previa presenta campos detectados, líneas, cliente/proveedor coincidente o nuevo, confianza, carpeta de destino en Drive y enlace al original. Una vez procesado, se pueden corregir datos y consultar el registro enlazado al fichero.

En la primera versión, una extracción suficientemente fiable puede crear el cliente/proveedor y el documento administrativo automáticamente. Campos obligatorios ausentes, conflicto de identidad o posible duplicado deben ir a revisión en vez de producir registros engañosos. Reintentar una ingesta es idempotente por hash/documento y no debe crear facturas, presupuestos o clientes duplicados.

### Agente administrativo común

El agente se ofrece como una única experiencia de chat dentro del SaaS. Los usuarios consultan en lenguaje natural sus propios datos y documentos: por ejemplo, facturas vencidas, total facturado en un periodo, presupuestos pendientes o contenido de un documento concreto. El agente usa servicios de lectura autorizados para datos contables y RAG filtrado para evidencia textual. Las acciones de escritura del agente requieren confirmación explícita y quedan registradas; en el MVP, la creación principal de registros ocurre mediante CRUD o ingesta documental. El agente no puede modificar facturas ni presupuestos ya enviados.

## Configuración, versiones y evaluación del agente común

El panel interno de plataforma administra una única configuración compartida: instrucciones, modelo/proveedor, parámetros de inferencia, herramientas disponibles, límites, políticas de seguridad y formato de citas. Los clientes no pueden modificar estos ajustes ni conectar sus propios modelos. Las diferencias entre respuestas se deben únicamente a los datos autorizados de cada tenant, no a configuraciones distintas del agente.

Cada cambio crea una versión inmutable con autor, fecha y motivo. Antes de promoverla a producción se ejecuta una batería de regresión; el administrador puede volver a la versión anterior. Los secretos se guardan cifrados fuera de las instrucciones y de las especificaciones exportables. El acceso a edición está restringido a administradores internos y queda auditado.

La suite de evaluación mantiene ejemplos representativos y comprueba:

- Extracción de campos, entidades y líneas de facturas/presupuestos, incluidos totales e impuestos.
- Clasificación correcta entre factura, presupuesto, documentación de proveedor y «por clasificar».
- Respuestas a consultas estructuradas con cifras exactas y filtros temporales.
- Recuperación RAG pertinente y citas correctas de fichero/página, midiendo recall@k y precisión con y sin reranking.
- Denegación de consultas de otro tenant y cumplimiento de permisos por rol (`admin` y `cliente`), incluido el escenario de un cliente compartido entre dos empresas (Paco, Juan y Alberto).
- Resistencia a instrucciones maliciosas incluidas en documentos y resultados recuperados.
- Negativa a modificar facturas o presupuestos enviados y propuesta de rectificativa o nueva versión.
- Comportamiento ante datos ambiguos, ausentes, duplicados y errores del proveedor.
- Latencia, consumo y coste dentro de los límites definidos.

Una versión que falle las pruebas críticas no se promueve. Los cambios del prompt, modelo, proveedor o herramienta se despliegan gradualmente y se monitorizan, ya que el cambio afecta a todos los tenants a la vez. La suite se ejecuta como experimento en Opik/Langfuse, de modo que cada versión candidata queda comparada con la de producción sobre el mismo conjunto de datos y las trazas en producción permiten detectar regresiones y revertir.

## Runtime, consultas e ingesta

### Consulta del agente

1. Autenticar usuario y tenant; comprobar permisos antes de recuperar datos. El `tenant_id` se fija en el servidor y se pasa a todas las herramientas; el modelo no puede cambiarlo.
2. Clasificar la pregunta como consulta estructurada, recuperación documental o híbrida.
3. Para cifras, estados y relaciones, ejecutar una consulta de dominio con parámetros y tenant obligatorio.
4. Para contenido documental, hacer búsqueda híbrida (pgvector + `tsvector`) filtrando por `tenant_id`, recuperar 30-50 candidatos, reordenarlos con el reranker y quedarse con los mejores (p. ej. 5) con un umbral mínimo de relevancia. Devolver citas con nombre de fichero y página.
5. Combinar resultados sin permitir que el modelo invente campos ausentes. Si las fuentes no bastan, indicarlo.
6. Guardar la conversación y métricas según la política de retención, evitando registrar secretos. Registrar la traza (recuperación, rerank, llamada al LLM, tokens, coste y versión del agente) con el mismo `trace_id` que los logs.

### Ingesta documental

- Recibir el fichero solo desde «Subir archivos» (o adjunto a una factura o presupuesto); avisar si su hash ya existe en el tenant.
- Aceptar tipos permitidos (PDF, JPEG/PNG, formatos ofimáticos acordados, TXT y CSV), validar MIME real, codificación de texto, tamaño y límites por tenant; rechazar el resto antes de subirlo.
- Guardar el original en un bucket privado con cifrado y acceso temporal controlado, y subirlo a `Entrada` en el Drive de la empresa.
- Extraer texto, tablas y coordenadas/páginas cuando estén disponibles; OCR para documentos escaneados.
- Clasificar como factura, presupuesto u otro documento, y determinar la dirección (emitido por la empresa o recibido de un proveedor) comparando el NIF/CIF del emisor con el del tenant.
- Normalizar nombres, identificadores fiscales, fechas, moneda, impuestos, totales y líneas.
- Verificar sumas: subtotal + impuestos − descuentos frente al total, con tolerancias explícitas por redondeo.
- Resolver cliente/proveedor por identificador fiscal y coincidencias secundarias; registrar nuevas entidades ausentes y enlazar las existentes.
- Persistir en transacción los datos normalizados, líneas, relaciones y estado del documento.
- Crear fragmentos y embeddings para RAG; indexar solo documentos que el tenant pueda consultar.
- Si no es factura, presupuesto ni documentación de un proveedor, guardar el tipo sugerido y un resumen breve, marcarlo como `unclassified` y no crear registros administrativos.
- Archivar el fichero en Drive en `Proveedores/<proveedor>`, `Facturas/<cliente>`, `Presupuestos/<cliente>`, `Revisión` o `Por clasificar`, después de confirmar la transacción. Si falla el movimiento, se reintenta sin repetir la extracción.
- Aplicar reintentos limitados con espera exponencial, detección de trabajos atascados, botón «Reintentar» para los fallidos, idempotencia y auditoría del resultado.
- Trazar cada paso (extracción, clasificación, llamada al LLM, validación, persistencia, embeddings, archivado) con el `trace_id` del documento para poder explicar por qué un documento terminó en `needs_review` o `failed`.

## Seguridad, privacidad y permisos

| Área | Medida |
| --- | --- |
| Aislamiento multi-tenant | `tenant_id` obligatorio tomado de la sesión; RLS en PostgreSQL; claves foráneas compuestas; clientes y proveedores compartidos duplicados por tenant; aislamiento en SQL, RAG, Drive, cachés y agente; pruebas de acceso cruzado que bloquean el despliegue |
| Roles | Solo `admin` (panel interno de la plataforma, sin acceso a la aplicación de las empresas) y `cliente` (un único usuario por empresa, con acceso solo a su tenant); verificación del rol en cada endpoint y operación; acceso del `admin` a datos de una empresa solo por soporte, con motivo y auditado |
| Agente común | Ajustes y credenciales solo accesibles al administrador interno; secretos cifrados y no enviados al cliente |
| Ficheros | Bucket privado, URLs firmadas de corta duración, límites de carga, validación MIME y análisis antimalware |
| Google Drive | Cada empresa conecta su propio Drive por OAuth con el permiso mínimo `drive.file` (solo los ficheros que crea la aplicación); la plataforma nunca recibe usuarios ni contraseñas de Google ni puede ver el resto del Drive; refresh token cifrado con clave KMS por tenant, descifrado solo en `drive-sync` y nunca visible para administradores, logs ni API; sin carpetas compartidas entre empresas; desconexión y revocación desde ajustes; auditoría de cada subida, movimiento y eliminación |
| Extracción IA | Validación de esquema, límites y consistencia; revisar baja confianza y duplicados; guardar procedencia |
| RAG y prompt | Fragmentos y documentos son datos no confiables; no permiten cambiar políticas ni superar permisos |
| Escrituras | Confirmación para acciones del agente; transacciones; registro de usuario, origen y cambios |
| Documentos enviados | Bloqueo de facturas y presupuestos enviados en los servicios de dominio y mediante trigger en PostgreSQL; hash del contenido enviado; correcciones solo con rectificativa o nueva versión |
| Autenticación | Verificación de email, contraseñas seguras, sesiones protegidas, limitación de intentos y MFA opcional |
| RGPD | Hosting UE, minimización, exportación y borrado, plazos de retención y acuerdos con proveedores |
| Observabilidad | Logs JSON y trazas de LLM sin secretos ni contenido completo de documentos; enmascarado de datos personales; Opik/Langfuse autoalojado en la UE con acceso solo para administradores internos; retención limitada de trazas |
| MCP (post-MVP) | OAuth 2.1 por usuario, scopes por herramienta, tenant y rol aplicados en servidor, rate limits por tenant, revocación de tokens, solo lectura en la primera versión y auditoría con `channel = mcp` |
| Copias de seguridad | Backups cifrados de PostgreSQL y ficheros; restauración probada |

## Infraestructura

| Servicio | Función |
| --- | --- |
| `proxy` | TLS y enrutamiento |
| `app` | Laravel: web, API, CRUD y dashboard |
| `queue` | Laravel Horizon, trabajos y notificaciones |
| `agent` | FastAPI: agente común y endpoints internos de ingesta |
| `worker` | Extracción, OCR, embeddings e indexación |
| `scheduler` | Laravel Scheduler: detecta documentos atascados y los vuelve a encolar |
| `drive-sync` | Subida de ficheros al Drive de cada empresa, creación de carpetas, archivado y envío a la papelera |
| `db` | PostgreSQL 16 con pgvector |
| `redis` | Colas, caché y rate limits |
| `object-storage` | Servicio S3 compatible, administrado o local en desarrollo |
| `observability` | Opik o Langfuse (trazas de LLM y evaluaciones) y agregador de logs JSON |
| `reranker` | Opcional: servicio de inferencia del cross-encoder si no se usa una API externa |
| `mcp` | Post-MVP: endpoint MCP del servicio FastAPI publicado a través del proxy |

Solo proxy expone puertos públicos. La app, runtime, base de datos, Redis y almacenamiento se comunican en red privada. Los secretos se inyectan desde entorno/gestor de secretos. Desplegar la misma imagen en staging y producción, ejecutar migraciones de forma controlada y supervisar salud de colas, almacenamiento e ingesta.

## Métricas

- CRUD: altas, modificaciones, errores de validación y actividad por tenant.
- Ingesta: documentos procesados, duración, fallos, reintentos, documentos atascados, campos de baja confianza, duplicados potenciales y correcciones.
- Google Drive: tiempo desde la subida hasta el archivado, ficheros en `Revisión`, reclasificaciones manuales, errores de la API y conexiones desconectadas.
- Por clasificar: documentos pendientes por tenant, antigüedad del más antiguo, reparto de las opciones elegidas (factura, presupuesto, proveedor, almacenar, eliminar) y tasa de documentos que el agente debería haber clasificado (los marcados como factura, presupuesto o proveedor).
- Calidad: exactitud de campos clave y consistencia de totales en un conjunto de pruebas etiquetado.
- Agente: latencia, tasa de respuestas con citas, errores de recuperación y consultas sin datos suficientes.
- Recuperación: recall@k y precisión con y sin reranking, latencia del reranker y porcentaje de candidatos descartados por umbral.
- Coste: tokens y coste de LLM, embeddings y reranking por tenant y por versión del agente (desde las trazas).
- MCP (post-MVP): tenants y usuarios conectados, llamadas por herramienta, errores de autorización y latencia.
- Sistema: latencia p50/p95, CPU/memoria, tamaño de PostgreSQL/índice, cola y uso de almacenamiento.
- Negocio: tenants activos, conversión, renovaciones y cancelaciones si se habilitan suscripciones.

## Plan de implementación por fases

**Fase 1 · Fundación y tenant (semanas 1-2)**

1. Crear monorepo, Docker Compose, CI y entornos.
2. Implementar registro, login, recuperación de contraseña, estructura de tenant y asistente de alta (con el paso «Conecta tu Google Drive», que se completa en la Fase 3).
3. Crear migraciones base, los roles `admin` y `cliente` (con la restricción de un solo usuario por empresa) y aislamiento de datos con RLS y claves foráneas compuestas.
4. Añadir tests de acceso cruzado desde el comienzo, con el escenario de un cliente compartido entre dos tenants.
5. Configurar logs estructurados en JSON con `trace_id` propagado entre Laravel, FastAPI y workers.

**Fase 2 · SaaS administrativo y CRUD (semanas 3-6)**

1. Implementar CRUD de clientes y proveedores, la gestión de la cuenta del usuario de la empresa y el panel de `admin` para dar de alta, suspender y reactivar empresas.
2. Implementar CRUD de facturas/presupuestos y líneas con validaciones de importes, estados, acción de envío, bloqueo tras el envío (servicio y trigger), facturas rectificativas y versiones de presupuesto.
3. Añadir historial de cambios, búsquedas, filtros, permisos y archivado.
4. Incorporar suscripciones Stripe si se decide monetizar mediante plan recurrente.

**Fase 3 · Ficheros e ingesta (semanas 7-10)**

1. Implementar almacenamiento privado, la sección «Subir archivos», validación, límites, aviso de duplicados y estados de procesamiento.
2. Construir extracción para PDF e imágenes con OCR cuando proceda.
3. Clasificar facturas/presupuestos y extraer emisor, cliente, proveedor, cabecera, impuestos, totales y líneas.
4. Implementar normalización, detección de duplicados, creación/enlace de entidades, idempotencia y revisión de excepciones.
5. Generar fragmentos, embeddings e índice textual (`tsvector`); indexar y borrar de forma coherente con la retención del fichero.
6. Desplegar Opik/Langfuse e instrumentar la ingesta con trazas por documento y enmascarado de datos personales.
7. Integrar Google Drive: conexión OAuth con permiso `drive.file` del Drive propio de cada empresa en el alta, cifrado del token con KMS, desconexión y reconexión, creación de la estructura de carpetas por tenant, subida a `Entrada` y archivado en `Proveedores/<proveedor>`, `Facturas/<cliente>`, `Presupuestos/<cliente>`, `Revisión` o `Por clasificar`. Solicitar la verificación de la pantalla de consentimiento OAuth de Google.
8. Implementar reintentos automáticos, detección de documentos atascados y botón «Reintentar».
9. Construir la sección «Por clasificar»: listado con tipo sugerido y resumen, y desplegable por fila con Es factura y Es presupuesto (elegir cliente, reprocesar con el tipo forzado y archivar en `Facturas/` o `Presupuestos/`), Es proveedor (elegir proveedor y archivar en `Proveedores/`), Verificado / Almacenar (mover a `Otros documentos/`) y Eliminar (papelera de Drive y borrado de copia, fragmentos y embeddings), con botón «Aplicar» y acciones en bloque.
10. Sincronizar las correcciones del panel con Drive (mover el fichero al reclasificar) y probar idempotencia, duplicados y aislamiento entre tenants en Drive.

**Fase 4 · Agente común y RAG (semanas 11-13)**

1. Implementar un único runtime y configuración global administrada en plataforma.
2. Añadir consultas permitidas a datos estructurados y recuperación híbrida (vector + texto) filtrada por tenant.
3. Añadir el reranker y medir recall@k y precisión con y sin él sobre el conjunto de evaluación.
4. Construir chat con citas a documentos y respuestas basadas en métricas exactas.
5. Añadir controles de permisos, confirmación de escritura, límites de uso y auditoría.
6. Instrumentar el runtime con trazas y ejecutar la suite de evaluación como experimento en Opik/Langfuse.

**Fase 5 · Validación y lanzamiento (semanas 14-16)**

1. Tests E2E para CRUD, bloqueo de documentos enviados, «Subir archivos», extracción, archivado en Drive, «Por clasificar», reintentos, revisión, deduplicación y consultas del agente.
2. Validar aislamiento entre tenants en API, SQL, objetos, Drive y RAG.
3. Medir calidad de extracción y ajustar umbrales de revisión.
4. Probar restauración de copias, exportación/borrado, accesibilidad y textos legales.
5. Beta con clientes y corrección de fallos antes de abrir el registro. Antes de abrirlo, la pantalla de consentimiento OAuth de Google debe estar verificada.

**Fase 6 · Servidor MCP (post-MVP, semanas 17-19)**

1. Implementar OAuth 2.1 por usuario, scopes por herramienta y revocación de tokens.
2. Exponer herramientas de solo lectura sobre los servicios de dominio y el RAG con citas.
3. Aplicar rate limits por tenant y auditoría con `channel = mcp`.
4. Tests de aislamiento entre tenants y de permisos a través de MCP; probar con Claude, Cursor y Windsurf.
5. Más adelante, herramientas de escritura con confirmación explícita.

## Estructura de repositorio propuesta

```text
admin-saas/
├── apps/
│   ├── web/                  # Laravel + Inertia + Vue + CRUD
│   │   ├── app/{Models,Policies,Services,Jobs,Http}
│   │   ├── database/migrations
│   │   ├── resources/js/{Pages,Components}
│   │   └── tests/{Feature,Unit}
│   └── agent/                # FastAPI: agente común, extracción y RAG
│       ├── app/{api,agent,rag,rerank,ingest,drive,models,observability,mcp}
│       └── tests/
├── infra/
├── docker-compose.yml
├── .github/workflows/ci.yml
└── docs/
```

## Prompt inicial para la IA constructora

```markdown
Eres el desarrollador principal de un SaaS administrativo multi-tenant. El producto permite gestionar usuarios, clientes, proveedores, facturas y presupuestos mediante CRUD manual y alta asistida por documentos.

Existe un único agente de IA común a todos los clientes, configurado por el administrador de plataforma. No crees un constructor de agentes ni configuración LLM por tenant. Al subir una factura o un presupuesto, el pipeline debe extraer todos los datos del documento y sus partes (cliente/receptor, proveedor/emisor y líneas), crear o relacionar las entidades ausentes dentro del tenant, evitar duplicados, guardar los datos normalizados y enlazarlos al fichero original. Los casos ambiguos o de baja confianza deben quedar para revisión.

Cada empresa conecta su propio Google Drive en el asistente de alta mediante OAuth de Google con el permiso drive.file (solo los ficheros que crea la aplicación); la plataforma nunca recibe contraseñas ni puede ver el resto del Drive, y el refresh token se guarda cifrado con KMS, sin que ningún administrador pueda verlo. En ese Drive se crea la estructura de carpetas (Entrada, Proveedores, Facturas, Presupuestos, Revisión, Por clasificar y Otros documentos). La única vía de entrada de documentos es la sección «Subir archivos» del menú principal: guarda una copia privada en S3, sube el fichero a Entrada y lanza la ingesta en el momento. No hay vigilancia del Drive: los ficheros añadidos directamente en Google Drive no se procesan. Después de procesarlo, el fichero se mueve a Proveedores/<proveedor> si lo emitió un proveedor, a Facturas/<cliente> o Presupuestos/<cliente> si lo emitió la empresa, a Revisión si es una factura o presupuesto ambiguo, o a Por clasificar si no es ninguna de esas cosas. La sección «Por clasificar» lista esos documentos con un desplegable por fila y un botón «Aplicar»: Es factura y Es presupuesto (el usuario elige el cliente, el agente reprocesa el documento con ese tipo forzado y se archiva en Facturas/<cliente> o Presupuestos/<cliente>), Es proveedor (el usuario elige el proveedor y se archiva en Proveedores/<proveedor>), Verificado / Almacenar (no crea registros y mueve el fichero a Otros documentos) y Eliminar (con confirmación: papelera de Drive y borrado de copia, fragmentos y embeddings, conservando la auditoría). Los fallos se reintentan automáticamente con espera exponencial, una tarea programada vuelve a encolar los documentos atascados y los que agotan los intentos quedan en failed con un botón «Reintentar». La ingesta es idempotente por hash y drive_file_id. Drive no es la fuente de verdad.

El agente responde usando servicios de consulta sobre los datos relacionales y RAG sobre los documentos del tenant. Las cifras y estados se obtienen de consultas estructuradas; los fragmentos vectoriales sirven para encontrar contenido y aportar citas. El agente nunca recibe SQL arbitrario ni puede cruzar datos de tenants.

La recuperación documental es híbrida (pgvector + búsqueda textual de PostgreSQL) y reordena los candidatos con un reranker antes de llamar al LLM. Todos los servicios emiten logs JSON con trace_id y las llamadas al LLM se trazan en Opik o Langfuse autoalojado. Tras el MVP se añadirá un servidor MCP con OAuth por usuario sobre los mismos servicios de dominio.

Stack: PHP 8.3 + Laravel 12 + Inertia + Vue 3 + TypeScript + Tailwind; Python 3.12 + FastAPI para ingesta y runtime; PostgreSQL 16 + pgvector; Redis 7; almacenamiento privado S3 compatible; Google Drive API v3; Opik/Langfuse; Docker Compose y GitHub Actions.

Reglas obligatorias:
1. Toda operación de negocio aplica tenant_id (tomado de la sesión, nunca del modelo) y autorización en servidor, con RLS en PostgreSQL. Un cliente o proveedor compartido por dos empresas es un registro distinto en cada tenant: si Paco y Juan tienen a Alberto como cliente, Paco solo puede ver las facturas que él emitió a Alberto. Añade tests de acceso cruzado con este escenario.
2. Los originales se almacenan privados; secretos cifrados y nunca incluidos en logs o respuestas.
3. Extracciones validadas por esquema, importes, procedencia e idempotencia.
4. El agente usa servicios permitidos, nunca SQL generado sin restricciones.
5. Búsqueda RAG siempre filtrada por tenant y con citas al fichero fuente.
6. Las acciones de escritura iniciadas por el agente requieren confirmación y auditoría.
7. Cada endpoint lleva pruebas de permisos y validación; cada worker/job tiene tests de reintentos y fallos.
8. Logs en JSON con trace_id y tenant_id; trazas de LLM sin secretos y con datos personales enmascarados.
9. Cada tenant solo accede a su propia carpeta de Drive y solo con el permiso drive.file; las subidas y movimientos de ficheros se auditan. La plataforma nunca borra ficheros del cliente por su cuenta: solo los envía a la papelera de Drive cuando un usuario pulsa Eliminar en «Por clasificar» y lo confirma.
10. Facturas y presupuestos son editables solo en borrador. Al enviarse quedan bloqueados (servicio de dominio + trigger en PostgreSQL) para cualquier canal, incluido el agente; solo cambia su estado. Las facturas enviadas se corrigen con una rectificativa y los presupuestos con una nueva versión.
11. Solo existen dos roles: admin (equipo de la plataforma, solo panel interno, sin tenant) y cliente (exactamente un usuario por empresa, restricción única por tenant_id). No hay invitaciones ni miembros.

Empieza por la Fase 1 del plan: estructura del repositorio, Docker Compose con healthchecks, CI, autenticación, tenant, logs JSON con trace_id y pruebas de aislamiento. Presenta el resultado antes de continuar.
```

## Riesgos y decisiones pendientes

| Riesgo | Mitigación |
| --- | --- |
| OCR o extracción incorrecta en escaneos/tablas complejas | Umbrales de confianza, validación de totales, revisión humana y conjunto de evaluación |
| Alta de clientes/proveedores duplicados | Normalización de identificadores fiscales, coincidencia secundaria y revisión de conflictos |
| Datos de distintos tenants en una respuesta (por ejemplo, Paco ve facturas de Juan a un cliente común) | Tenant fijado desde la sesión, RLS obligatorio, registros separados por tenant para clientes compartidos, RAG filtrado en la consulta y pruebas end-to-end que bloquean el despliegue |
| Documentos maliciosos o con instrucciones para el agente | Validación de formatos, análisis de ficheros y tratamiento del contenido como datos no confiables |
| Cambio de proveedor/modelo común afecta a todos | Configuración versionada, pruebas de regresión y despliegue gradual/rollback |
| Coste de OCR, LLM, embeddings y reranking | Límites por tenant, métricas de coste desde las trazas y cuotas configurables |
| Datos personales en trazas de LLM | Autoalojamiento en la UE, enmascarado, acceso restringido y retención corta |
| Latencia añadida por el reranker | Limitar candidatos, umbral de relevancia y medir p95; reranker local si la API es lenta |
| Modificación de una factura o presupuesto ya enviado | Bloqueo en servicio y en base de datos, hash del contenido enviado, rectificativas y versiones, y tests por cada canal (web, API, agente, MCP) |
| Envío por error de un documento incompleto | Validación previa y confirmación explícita antes de marcarlo como enviado; corrección posterior mediante rectificativa |
| Fichero archivado en una carpeta equivocada | Dirección por NIF/CIF del tenant, `Revisión` ante dudas, reclasificación desde el panel que mueve el fichero y auditoría de movimientos |
| El cliente sube ficheros directamente a Google Drive esperando que se procesen | Aviso claro en «Subir archivos» y en la ayuda de que es la única vía; detección de subidas directas como posible evolución |
| Factura o presupuesto enviado por error a «Por clasificar» | Opciones Es factura / Es presupuesto / Es proveedor en el desplegable, que lo reprocesan con el tipo indicado; estos casos alimentan la suite de evaluación |
| Opción equivocada en el desplegable de «Por clasificar» | Botón «Aplicar» en lugar de acción inmediata, confirmación para Eliminar y corrección posterior desde la ficha del documento o el CRUD |
| Eliminación por error de un documento válido | Confirmación previa, papelera de Drive con 30 días para recuperarlo y auditoría |
| Fichero que falla siempre al procesarse | Reintentos limitados, detección de trabajos atascados, estado `failed` visible con su error, botón «Reintentar» y copia segura en S3 |
| El cliente revoca el acceso o caduca el token | Estado `disconnected`, «Subir archivos» desactivado, archivados pendientes en espera, aviso al usuario de la empresa y finalización de lo pendiente al reconectar |
| La empresa pierde el acceso de su único usuario (empleado que se va, contraseña olvidada) | Recuperación de contraseña por email, cambio de email desde la cuenta y, como último recurso, reasignación verificada por el `admin` con auditoría |
| El Drive está conectado con la cuenta personal de un empleado que se va | Recomendar en el alta una cuenta de Google de la empresa y permitir reconectar con otra cuenta |
| Robo de tokens de Google | Permiso mínimo `drive.file`, cifrado de sobre con clave por tenant en KMS, descifrado solo en `drive-sync`, sin exposición en panel, logs ni API, y revocación inmediata desde ajustes |
| El cliente mueve o borra ficheros a mano en Drive | Copia inmutable en S3, enlace por `drive_file_id` y aviso en la ficha si el fichero ya no está, sin perder los datos extraídos |
| Abuso o fuga de datos vía MCP | OAuth por usuario, scopes, solo lectura inicial, rate limits, auditoría y tests de acceso cruzado |

## Fuera de alcance

- **Streamlit como interfaz.** La interfaz de clientes y la de administración interna se construyen con Laravel + Inertia + Vue. La revisión de evaluaciones y trazas se hace en Opik/Langfuse, así que no hace falta una segunda interfaz.
- **Vigilancia automática del Drive.** Por ahora no se detectan ni se analizan los ficheros añadidos directamente en Google Drive: ni consultas periódicas de cambios ni revisión diaria. Si se retoma, exigirá el permiso completo `drive`, la verificación de seguridad de Google (evaluación CASA anual) y revisar la promesa de que la plataforma no puede ver el resto del Drive del cliente.

Decisiones comerciales aún por cerrar: precio/periodicidad, límites de almacenamiento y usuarios, proveedor de LLM/OCR, retención de datos, si el alta extraída se confirma siempre o se permite automática por umbral de confianza, si se renombran los ficheros al archivarlos (por ejemplo, `2026-10-15_F-2026-001.pdf`), y si el envío al cliente se hace desde el SaaS por email o el usuario envía por su cuenta y lo marca como enviado (y, en el primer caso, cuándo se incorpora VeriFactu).
