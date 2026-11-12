# ADR-012 — Facturación conforme a Verifactu

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-FA-02, RF-FA-04, RF-FA-08, RF-VF-01, RF-VF-02, RF-VF-03, RF-VF-04, RF-VF-05, RF-VF-06, RF-VF-07, RN-12, RN-13, RN-F-01, RN-F-02, RN-F-03, RN-F-04, RN-F-06, RN-F-07
- **Se cierra en:** Bloque 12

## Contexto

Kapataz emite facturas válidas desde la primera factura real, con el sistema VERI*FACTU activo (§1.3). KodigoLab es el productor del sistema y firma una declaración responsable por cada versión (RF-VF-06).

**Situación normativa** (aviso legal de §1 del plan, a 11 de noviembre de 2026):

- Normas de referencia: Real Decreto 1007/2023, Orden HAC/1177/2024 y especificaciones técnicas de la AEAT.
- Según el Real Decreto-ley 15/2025, los productores solo pueden ofrecer sistemas adaptados desde el 29 de julio de 2025. Las sociedades deben usarlos antes del 1 de enero de 2027, y el resto, autónomos incluidos, antes del 1 de julio de 2027.
- El 5 de octubre de 2026, Hacienda publicó la previsión de aplazar las obligaciones pendientes de empresarios y profesionales a octubre de 2028. No hay norma en el BOE y la AEAT sigue citando las fechas de 2027.
- Entendemos que ese aplazamiento no afecta a los productores, cuya obligación ya es exigible. La nota no lo dice de forma expresa: está pendiente de confirmar con el asesor fiscal.
- La misma nota anuncia una segunda modificación de los ámbitos de aplicación y de aspectos técnicos, para converger con la factura electrónica y con ViDA. Hay que revisar las especificaciones de la AEAT antes de empezar el Bloque 12.

**Garantía de lanzamiento.** Verifactu se construye al final, pero ningún cliente real emite facturas hasta cerrar el Bloque 12, con la declaración responsable firmada y la validación de un asesor fiscal. Para garantizarlo, el registro está cerrado hasta la 1.0.0 (RN-13) y las cuentas habilitadas solo emiten facturas con la marca de demostración (RN-F-09).

## Opciones consideradas

1. **Modalidad VERI*FACTU con envío mediante un proveedor externo por API**
   - Ventajas: sin firma de registros ni custodia de claves; el proveedor gestiona la conexión con la AEAT; se puede cambiar detrás de `BillingRecordSubmissionPort`.
   - Inconvenientes: un subencargado más que recibe los registros; cada cliente debe autorizar a quien envía; preguntas abiertas sobre el reparto de papeles (ver «Pendiente para cerrar»); coste por proveedor aún desconocido.
2. **Modalidad VERI*FACTU con envío directo a la AEAT como colaborador social** (`VerifactuAeatSubmission`)
   - Ventajas: sin intermediario ni coste de proveedor; un tratamiento de datos menos.
   - Inconvenientes: KodigoLab tendría que hacerse colaborador social, enviar con su certificado y gestionar conexión, reintentos e incidencias; más riesgo propio.
3. **Modalidad no VERI*FACTU** (registros conservados en el propio sistema)
   - Ventajas: sin envío de cada registro a la AEAT.
   - Inconvenientes: exige firmar los registros y custodiar claves; el plan la descarta (RF-VF-03).

## Decisión (propuesta)

**Desde el Bloque 2, sin depender del proveedor:**

- Factura emitida inmutable, con trigger además del dominio (RN-F-02).
- Numeración sin huecos por cuenta, serie y año, con bloqueo de fila (RN-F-01).
- Rectificativas R1 a R4, por sustitución o por diferencias, con referencia a las facturas rectificadas (RN-F-03).
- `BillingRecord` con huella SHA-256 encadenada en una sola cadena por cuenta, con altas, subsanaciones y anulaciones. El estado «anulada» se deduce de la cadena, sin modificar la factura (RN-F-07).
- Toda operación que añade un registro bloquea primero la cabeza de la cadena de la cuenta (`billing_chain_heads`, `SELECT … FOR UPDATE`) y después el contador de la serie, siempre en ese orden y en la misma transacción (RN-F-07, ADR-004). Así, dos emisiones simultáneas no enlazan con el mismo registro anterior aunque sean de series distintas (F y R). RN-F-04 se comprueba con el contador ya bloqueado.
- Contenido canónico con los mismos campos que `RegistroAlta` y `RegistroAnulacion` de los esquemas de la AEAT (Orden HAC/1177/2024, arts. 7 y 13).
- `BillingRecordSubmissionPort` con `NullBillingRecordSubmission` hasta el Bloque 12.

**En el Bloque 12:**

- Solo modalidad VERI*FACTU (RF-VF-03). Cada registro se envía a la AEAT mediante el proveedor y la factura lleva la mención y el QR (RF-VF-02).
- Adaptador `VerifactuProviderSubmission`. `VerifactuAeatSubmission` queda como alternativa si KodigoLab se hace colaborador social.
- El Bloque 12 convierte el contenido canónico a XML y calcula la huella con el algoritmo oficial.
- Envíos fallidos reintentados y visibles; rechazos avisados con motivo y forma de corregirlos (RF-VF-04). Corregir y reenviar funciona también con la cuenta en solo lectura (RN-12).
- Exportación de registros a petición de la Administración (RF-VF-05).
- **Autorización de cada cliente** antes de su primera factura (RF-VF-07), guardada en `submission_authorizations`: Anexo I de la Resolución de 18 de diciembre de 2024, a favor de quien envía con su certificado (el proveedor, o KodigoLab si se hace colaborador social). Firma manuscrita con copia del DNI, certificado cualificado o firma electrónica avanzada, dentro de la app. Aceptar unas condiciones no sirve. No hace falta ningún trámite en la sede de la AEAT. Se conserva mientras dure la relación y cuatro años después (art. 66 de la Ley General Tributaria) y queda bloqueada tras el borrado de la cuenta (RN-12). Mientras no la otorgue, el usuario puede usar el resto de la app.
- El proveedor de envío es subencargado del tratamiento.

## Pendiente para cerrar

**1. Contraste normativo** (Bloque 12, `arquitecto-python` + `seguridad-ia`):

- Comparar los esquemas de producción con los de preproducción usados para el modelo. En noviembre de 2026, la lista de exenciones llegaba a E8 en preproducción y a E6 en la orden.
- Confirmar en el documento de validaciones que `ImporteTotal` es base más cuota, sin restar la retención de IRPF ni la garantía.
- Revisar si la modificación técnica anunciada el 5 de octubre de 2026 ha cambiado el registro.
- Revisar el BOE antes de lanzar.

**2. Elección del proveedor** (decide Borja). Comparar precio, autorización que exige a cada cliente, datos que recibe y dónde los trata, frente a la alternativa de colaborador social. Datos necesarios: respuestas de los proveedores a estas preguntas:

- **Autorización:** ¿a favor de quién se otorga, del proveedor, de KodigoLab o de ambos?
- **Colaboración social:** al haber dos intermediarios, ¿exige la AEAT el convenio de colaboración social a los dos? (preguntas frecuentes de desarrolladores de la AEAT, §16.3).
- **Huella:** ¿quién calcula la huella y el encadenamiento, Kapataz o el proveedor? ¿Admite un registro ya formado o solo los datos de la factura?
- **`SistemaInformatico`:** ¿qué sistema figura en ese bloque de cada registro, el de Kapataz o el del proveedor? De ello depende quién firma la declaración responsable como productor.
- **Servicio de consulta:** ¿da acceso a la consulta de la AEAT para conciliar el estado de cada registro (correcto, aceptado con errores o anulado) con `billing_records`, buscando por `external_ref`? La consulta va por ejercicio y mes, con paginación.

**3. Confirmación con el asesor fiscal** de que el aplazamiento a 2028 no afecta al productor.

**4. Cierre:** registros, huella y QR verificados; envío aceptado en el entorno de pruebas de la AEAT; autorización resuelta; declaración responsable firmada y validación fiscal del asesor.

## Consecuencias

- **Positivas**
  - La base fiscal existe desde el Bloque 2; el Bloque 12 añade formato, envío y autorización sin rehacer el modelo.
  - Cambiar de proveedor, o pasar a colaborador social, es cambiar de adaptador.
  - Sin custodia de claves para firmar registros.
- **Negativas y mitigación**
  - Dependencia del proveedor → puerto propio, reintentos con estado visible, exportación de registros y contrato de encargo como subencargado.
  - Fricción de la autorización antes de la primera factura → no bloquea el resto de la app y se firma dentro de ella.
  - Incertidumbre normativa → contenido canónico alineado con los campos de la AEAT desde el Bloque 2 y contraste normativo al empezar el Bloque 12.
  - Si en `SistemaInformatico` figura el sistema del proveedor, cambia quién es productor → se resuelve antes de firmar ninguna declaración responsable.
- **Qué haría reconsiderarla**
  - Que la AEAT exija el convenio de colaboración social también a KodigoLab, lo que acerca el coste del envío directo.
  - Que las respuestas de los proveedores sobre autorización, datos o precio no sean aceptables.
  - Que una norma publicada en el BOE cambie la modalidad, el registro o las fechas que afectan al productor.

## Verificación

- **import-linter:** el proveedor solo se conoce en `kapataz.infrastructure.fiscal`; dominio y aplicación solo ven `BillingRecordSubmissionPort`.
- **Bloque 2:**
  - `tests/integration/billing/test_numeracion_concurrente.py`, `@pytest.mark.req("RN-F-01")`. Incluye emisiones simultáneas de las series F y R en la misma cuenta: la cadena no se bifurca. `@pytest.mark.req("RN-F-07")`.
  - `tests/integration/billing/test_inmutabilidad_sql.py`, `@pytest.mark.req("RN-F-02")`.
  - `tests/unit/billing/test_billing_record_campos_aeat.py`: cada campo obligatorio del esquema tiene su dato. `@pytest.mark.req("RN-F-07")`.
  - `tests/unit/billing/test_cadena_unica.py`: una subsanación y una anulación se encadenan en la misma cadena que las altas. `@pytest.mark.req("RN-F-07")`.
- **Bloque 8:** `kapataz verify-billing-chain` detecta una alteración hecha por SQL.
- **Bloque 12:**
  - Huella y QR contrastados con la especificación oficial. `@pytest.mark.req("RF-VF-01")` y `@pytest.mark.req("RF-VF-02")`.
  - Rechazo con motivo visible y reintento de envío fallido. `@pytest.mark.req("RF-VF-04")`.
  - Subsanación con la cuenta en solo lectura. `@pytest.mark.req("RN-12")`.
  - Sin autorización no se emite la primera factura y el resto de la app funciona. `@pytest.mark.req("RF-VF-07")`.
  - Envío aceptado en el entorno de pruebas de la AEAT, anotado en el PR.
