# Consulta a proveedores de envío VERI*FACTU

**Asunto:** Consulta previa a contratar: envío de registros VERI*FACTU por API para un programa de facturación

**De:** Borja Peón, KodigoLab · **Fecha:** noviembre de 2026

Buenos días:

## Qué necesitamos

Estamos eligiendo proveedor para enviar a la AEAT los registros de facturación de nuestros clientes. Necesitamos respuesta a las preguntas de abajo para comparar ofertas.

Kapataz es un programa de facturación por suscripción para autónomos de oficio. KodigoLab es el productor del sistema y firma la declaración responsable. Generamos los registros y el QR, con los mismos campos que `RegistroAlta` y `RegistroAnulacion` de los esquemas de la AEAT; queremos delegar el envío por API, solo en modalidad VERI*FACTU. Solo emitimos facturas completas a destinatarios con NIF español. Lanzamos en 2027, con decenas de clientes al principio.

## Preguntas

### Representación y colaboración social

1. La autorización de cada autónomo (Anexo I de la Resolución de 18 de diciembre de 2024), ¿se otorga a favor de ustedes, al nuestro o a ambos?
2. ¿Tienen firmado el acuerdo de colaboración social con la AEAT? ¿Necesitamos firmarlo también nosotros al intervenir dos intermediarios? Las aclaraciones de la AEAT a desarrolladores (apartado 16.3) apuntan a que sí.
3. ¿Vale que el autónomo firme la autorización dentro de nuestro programa, con firma electrónica o manuscrita digitalizada? ¿Qué tipo de firma exigen?
4. ¿Quién custodia la autorización firmada y durante cuánto tiempo?

### Servicio

5. ¿Cómo nos comunican las respuestas de la AEAT: aceptado, aceptado con errores y rechazado? ¿Por webhook o por consulta?
6. ¿Gestionan los reintentos cuando la AEAT no responde? ¿Con qué frecuencia y durante cuánto tiempo?
7. ¿Admiten registros de subsanación y de anulación?
8. ¿Hay entorno de pruebas conectado al de la AEAT?
9. ¿Qué disponibilidad garantizan y cómo avisan de las incidencias?
10. ¿Dan acceso al servicio de consulta de la AEAT, para comparar el estado de los registros que guarda la AEAT con el nuestro? ¿Conservan nuestra referencia externa (`RefExterna`) en cada registro?

### Datos

11. ¿Qué datos de los registros conservan, dónde y durante cuánto tiempo? ¿Todo dentro de la Unión Europea?
12. ¿Firman un contrato de encargo del tratamiento como subencargados?
13. Cuando un cliente nuestro se da de baja, ¿qué pasa con sus datos y con su autorización?

### Precio y salida

14. Precio por registro o por cliente, mínimos y permanencia.
15. Si cambiamos de proveedor, ¿cómo se traspasan las autorizaciones y el histórico?

### Cambios normativos

16. Hacienda anunció el 5 de octubre de 2026 que prevé aplazar las obligaciones pendientes a octubre de 2028 y modificar después aspectos técnicos del sistema, para converger con la factura electrónica. ¿Siguen admitiendo envíos voluntarios hasta esa fecha? ¿Adaptarán su API a esos cambios técnicos, y está incluido en el precio?

### Registro y sistema informático

17. ¿Quién calcula la huella y el encadenamiento de cada registro: nosotros o ustedes? ¿Admiten un registro ya formado, o solo los datos de la factura?
18. ¿Qué sistema figura en el bloque `SistemaInformatico` de cada registro: el nuestro o el de ustedes? De eso depende quién firma la declaración responsable como productor.
19. Si la AEAT o su servicio no responden y el registro se envía tarde, ¿marcan ustedes la incidencia en el envío o debemos indicarla nosotros?

## Plazos

Elegiremos proveedor antes de construir el módulo de envío. Si alguna pregunta necesita más contexto, indíquennos cuál.

Muchas gracias. Un cordial saludo,

Borja Peón
KodigoLab
