# ADR-0020: Impago sin corte de acceso (solo se desactiva la IA) y email únicamente para recuperar la contraseña

- **Estado:** Aceptada
- **Fecha:** 2026-10-29
- **Modifica:** [ADR-0019](0019-cobro-por-transferencia.md) (recordatorios por email y paso a solo lectura por impago)

## Contexto

[ADR-0019](0019-cobro-por-transferencia.md) preveía recordatorios de pago por email y, tras 15 días de impago, el paso de la empresa a solo lectura. Se quiere que el impago no impida a la empresa seguir trabajando con sus datos, y limitar al mínimo los emails que envía la aplicación (menos dependencia del proveedor de correo, menos riesgo de spam y menos coste).

## Decisión

### Email

- La aplicación **solo envía un tipo de email: el de recuperación de contraseña**.
- Todo lo demás se comunica **dentro de la aplicación** (banner o aviso persistente y centro de avisos): cuota pendiente o vencida, límites al 80 % y al 100 %, Drive desconectado, documentos en revisión o en «Por clasificar», factura de la cuota disponible.
- No hay email de verificación al registrarse. Para reducir errores al escribir el email, el registro pide introducirlo dos veces y lo muestra en ajustes, donde se puede cambiar.
- Las alertas técnicas al `admin` (caídas, errores, colas atascadas) no las envía la aplicación: las envían las herramientas de monitorización (UptimeRobot o Better Stack y GlitchTip o Sentry).

### Impago: modo sin IA

Pasados N días del vencimiento (configurable, inicialmente 15) sin pago registrado, la empresa entra en **modo sin IA**. **No se corta el acceso.** Se desactiva solo lo que usa IA o genera gasto variable:

| Función | En modo sin IA |
| --- | --- |
| Iniciar sesión, ajustes, cuenta, factura de la cuota | Disponible |
| CRUD manual de clientes, proveedores, facturas y presupuestos (incluidos marcar como enviado, rectificativas y nuevas versiones) | Disponible |
| Consultar, filtrar y buscar en listados (consultas SQL normales) | Disponible |
| Ver y descargar documentos ya procesados y sus datos | Disponible |
| «Por clasificar»: **Verificado / Almacenar** y **Eliminar** | Disponible |
| «Subir archivos» | Disponible: el fichero se guarda en `Entrada` del Drive de la empresa y queda **pendiente de procesar**. No se analiza ni se guarda la copia privada en S3 hasta que se registre el pago |
| Análisis de documentos (extracción, clasificación, embeddings e indexación) | Desactivado |
| Chat con el agente y búsqueda semántica en documentos | Desactivado |
| «Por clasificar»: **Es factura**, **Es presupuesto** y **Es proveedor** (reprocesan con IA) | Desactivado |

- La interfaz muestra un aviso persistente con el importe pendiente y la referencia de pago, y los botones de las funciones de IA aparecen desactivados con una explicación, no ocultos.
- **Al registrar el pago**, el `admin` reactiva la IA al momento y los documentos pendientes de procesar se encolan automáticamente, en orden de subida y respetando los límites del mes.
- **Nunca se borran datos por impago.**
- El mismo modo sin IA se usa cuando una empresa agota sus límites mensuales de documentos, consultas o gasto de IA, pero solo para la parte agotada y hasta el mes siguiente o la compra de un paquete adicional.
- El bloqueo se aplica en el servidor (servicio de dominio y política) antes de encolar cualquier trabajo de IA, no solo en la interfaz. Los workers vuelven a comprobar el estado de la empresa antes de llamar al modelo.

## Alternativas consideradas

- **Solo lectura por impago (ADR-0019):** protege el coste, pero impide trabajar con datos que no generan gasto y perjudica la relación con el cliente.
- **Cortar el acceso:** el cliente no podría ni consultar sus datos; desproporcionado y problemático con el RGPD (acceso a sus propios datos).
- **Recordatorios por email:** más eficaces para cobrar, pero aumentan la dependencia y el riesgo de spam del correo; se sustituyen por avisos en la aplicación.

## Consecuencias

- El impago solo cuesta la parte fija de infraestructura de esa empresa; el gasto variable (IA) se detiene.
- Un cliente que no entra en la aplicación no se enterará de que tiene la cuota pendiente: el `admin` puede contactarle por su cuenta (email o teléfono) desde fuera de la aplicación.
- Sin verificación de email al registrarse, un email mal escrito impediría recuperar la contraseña; se mitiga con la doble introducción y la reasignación verificada por el `admin` ([ADR-0006](0006-roles-admin-cliente.md)).
- Los tests cubren cada función de la tabla en modo sin IA, por todos los canales (web, API, agente y workers).
