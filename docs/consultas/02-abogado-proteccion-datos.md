# Consulta legal: contrato y protección de datos de un programa de facturación por suscripción

**Asunto:** Solicitud de presupuesto: contrato y protección de datos de un programa de facturación por suscripción

**De:** Borja Peón, KodigoLab · **Fecha:** noviembre de 2026

Buenos días:

Busco un despacho para el encargo que describo abajo. Les agradecería que me indicaran si lo pueden asumir, el presupuesto y el plazo.

## Qué necesitamos

Que redacten o revisen cuatro textos antes del lanzamiento, y que confirmen las decisiones que ya hemos tomado:

1. Condiciones de uso del servicio.
2. Contrato de encargo del tratamiento, como anexo de las condiciones.
3. Política de privacidad.
4. Aviso de uso de inteligencia artificial.

## El servicio

Kapataz es un programa web de KodigoLab para autónomos de oficio. El autónomo crea presupuestos y facturas por voz o por texto y paga una cuota mensual. El programa envía los registros de sus facturas a la AEAT (sistema VERI*FACTU).

- **Quién es quién:** el autónomo es responsable de los datos de sus clientes; KodigoLab es encargado del tratamiento.
- **Dónde están los datos:** en servidores de la Unión Europea.
- **Subencargados:**
  - el proveedor que envía los registros a la AEAT, que recibe el nombre y el NIF del cliente final, los importes y la descripción de la obra;
  - el alojamiento;
  - el correo;
  - las copias de seguridad;
  - Anthropic, la empresa de la IA.

## Decisiones que queremos que confirmen

### Fin del servicio y borrado

Si el autónomo deja de pagar, tiene 14 días con el programa completo y después 90 días en solo lectura, en los que puede consultar y exportar todo. La baja voluntaria sigue el mismo camino al acabar el periodo pagado. Pasados los 90 días, borramos la cuenta.

Entendemos que:

- La exportación cumple la devolución de los datos del art. 28.3.g del RGPD, si el contrato lo dice de forma expresa.
- Conservar las facturas es obligación del autónomo, no nuestra (art. 29.2.e de la Ley General Tributaria). Se lo avisamos antes de borrar.
- Podemos conservar bloqueada la autorización que firma el autónomo para enviar sus registros a la AEAT (arts. 32 y 33.4 de la LOPDGDD). No hay plazo legal; proponemos la duración de la relación y cuatro años más.

**¿Es correcto? ¿Qué plazo de conservación recomiendan para la autorización?**

### NIF del cliente final

El programa exige el NIF de cada cliente del autónomo, también si es un particular. El registro que se envía a la AEAT identifica al destinatario de la factura, y el tipo de IVA de una reforma depende de quién es. No emitimos facturas simplificadas.

**¿Es conforme con el principio de minimización? ¿Qué base jurídica debe citar el autónomo ante su cliente?**

### Calendario de VERI*FACTU

Hacienda anunció el 5 de octubre de 2026 que prevé aplazar a octubre de 2028 la obligación de los autónomos. Lanzamos en 2027, así que al principio nuestros clientes enviarán sus registros de forma voluntaria.

**¿Cambia eso la base jurídica del envío o lo que debe decir el contrato?**

### Anthropic (IA)

Antes de enviar un texto a Anthropic sustituimos nombres, NIF, direcciones y teléfonos por etiquetas. Lo tratamos igualmente como subencargado, porque los datos seudonimizados siguen siendo personales.

Contratamos con Anthropic Ireland, Limited, que es la entidad que firma con los clientes del Espacio Económico Europeo. Los datos se almacenan en Estados Unidos y las peticiones pueden procesarse en Estados Unidos, Europa, Asia o Australia: la API no ofrece tratamiento solo en la Unión Europea. Su contrato de tratamiento incluye cláusulas contractuales tipo (módulos 2 y 3), y su soporte nos ha confirmado por escrito que el módulo 3 nos cubre como encargados. No nos consta que Anthropic esté adherida al Marco de Privacidad de Datos UE-EE. UU.

Tres datos más del contrato de Anthropic:

- El importador de los datos es la entidad que firma con nosotros, es decir, Anthropic Ireland. Ningún documento público dice qué garantía cubre el paso de Irlanda a la matriz estadounidense, Anthropic, PBC.
- Anthropic se compromete a facilitar, si se le pide, la información necesaria para la evaluación de impacto de la transferencia (sección I.4 del contrato de tratamiento).
- El contrato se rige por la ley irlandesa, con arbitraje en Dublín. Si el contrato lo permite, Anthropic puede anonimizar los datos de la organización para investigación o estadística y conservarlos más tiempo.

La lista de subencargados y las filiales con acceso a los datos están en `https://trust.anthropic.com/subprocessors` y en las preguntas frecuentes de `https://trust.anthropic.com/faq`.

Anthropic borra las entradas y salidas en 30 días. Si sus sistemas de seguridad marcan un contenido, puede conservarlo hasta 2 años, y las puntuaciones de clasificación, hasta 7. Hemos pedido la retención cero, que depende de su aprobación.

**Si contratamos con una entidad irlandesa, ¿hay transferencia internacional por nuestra parte, o solo la que hace Anthropic dentro de su grupo? ¿Basta con las cláusulas tipo y una evaluación de impacto de la transferencia? ¿Pueden revisar esa evaluación? ¿Cómo debe reflejar el contrato con el autónomo los plazos de conservación de Anthropic?**

### Stripe (cobro de la cuota)

Solo trata datos de nuestros suscriptores. Según su contrato, actúa como encargado para el cobro y como responsable independiente para el fraude y el cumplimiento normativo. **¿Cómo debe explicarlo la política de privacidad?**

### Aviso de IA

Avisamos del uso de IA en la primera interacción, por el art. 50 del Reglamento de IA. **¿Es suficiente? ¿Hace falta algo más por la normativa española?**

## Lo que necesitamos que redacten

- **Limitación de responsabilidad:**
  - El autónomo responde del contenido de sus facturas y de atender los rechazos de la AEAT.
  - KodigoLab responde de que el programa cumpla la normativa de facturación.
  - Queremos saber hasta dónde podemos limitarla entre profesionales.
- **Cláusulas sobre impago, baja, solo lectura, exportación y borrado.**
- **Cambios del contrato de encargo:** entendemos que publicarlos en la web no basta y que hay que notificarlos al autónomo y obtener su aprobación. Queremos un procedimiento sencillo.
- **Lista de subencargados** y forma de comunicar los cambios.

## Qué les enviaremos

El detalle técnico de qué datos se tratan, dónde y durante cuánto tiempo, y los contratos de tratamiento de Anthropic y de Stripe. Si necesitan algo más para dar un presupuesto, indíquennos qué.

Muchas gracias. Un cordial saludo,

Borja Peón
KodigoLab
