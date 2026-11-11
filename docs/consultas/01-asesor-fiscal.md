# Consulta fiscal: IVA en la facturación de reformas por fases

**Asunto:** Consulta fiscal: IVA en reformas facturadas por fases (programa de facturación)

**De:** Borja Peón, KodigoLab · **Fecha:** noviembre de 2026

Buenos días:

Busco un asesor fiscal que responda por escrito a la consulta de abajo. Le agradecería que me indicara si puede hacerlo, el precio y el plazo.

## Qué necesitamos

Que confirme o corrija seis reglas de IVA antes de programarlas, y que responda dos preguntas aparte sobre VERI*FACTU. Estamos construyendo Kapataz, un programa de facturación para autónomos de oficio (albañiles, pintores, fontaneros, electricistas). El programa decidirá el tipo de IVA y calculará las facturas, así que un error se repetiría en todas las facturas de todos los clientes.

Las reglas salen de la Ley del IVA y de consultas de la Dirección General de Tributos (DGT) que hemos leído por nuestra cuenta. Dos asesores nos dieron antes respuestas distintas entre sí en los puntos 1 y 3.

Un dato de contexto: el programa solo emite facturas completas, con el NIF del destinatario también cuando es un particular. No emite facturas simplificadas.

## Las seis reglas

### 1. El anticipo lleva el tipo de la obra

Una reforma de vivienda que cumple los requisitos del art. 91.Uno.2.10º de la Ley del IVA va entera al 10 %: material, mano de obra y anticipos. El anticipo se factura al cobrarlo (art. 75.Dos) y al tipo de la obra (art. 90.Dos).

Ejemplo: el cliente paga 6.000 € antes de empezar una reforma al 10 %. Factura de anticipo: base 5.454,55 €, IVA 545,45 €.

Un asesor nos indicó que ese anticipo va al 21 % «por ser para material». Entendemos que no, por las consultas V2662-13, V1392-26 y V0624-23. **¿Es correcto?**

### 2. Si el material supera el 40 % al terminar

Toda la obra pasa al 21 %. Entendemos que lo ya facturado al 10 % a un particular no se puede rectificar al alza (art. 89.Tres.1º) y que el autónomo debe ingresar la diferencia de su bolsillo (art. 89.Cinco; consulta V0624-23).

Ejemplo: anticipo facturado de 1.000 € de base al 10 %. Al final el material supera el 40 %. La factura final va al 21 % y el autónomo ingresa 110 € más por el anticipo.

**¿Es correcto? ¿Cómo declara el autónomo esos 110 €?**

### 3. Si se ha facturado más de lo que se ha hecho

No emitimos una factura final negativa. Emitimos una factura rectificativa de la última fase, por la diferencia (art. 80.Dos de la Ley del IVA y art. 15 del Reglamento de facturación).

Ejemplo: presupuesto de 10.000 €; anticipo de 3.000 € y certificación de 4.000 € ya facturados. El cliente reduce la obra y el servicio queda en 6.000 €. Rectificativa de la certificación por −1.000 € de base.

Un asesor nos propuso una factura final negativa que explicara lo descontado. **¿Cuál de las dos es la forma correcta?**

Si la diferencia es mayor que la última fase, una sola rectificativa rectificaría varias facturas anteriores. La comunicaríamos a la AEAT como rectificativa por diferencias de la clase R1 (art. 80.Uno y Dos). **¿Es correcto?**

### 4. Retención de garantía

Solo la admitimos en la factura final. La factura lleva el total con todo su IVA, y un porcentaje de la base queda pendiente de cobro hasta la fecha pactada.

Ejemplo: factura final de 10.000 € de base al 21 %, con un 5 % de garantía a 12 meses. Total 12.100 €; se cobran 11.600 € y quedan 500 € aplazados.

Nos basamos en la consulta V0942-16: al entregar la obra, la base incluye lo retenido. **¿Es correcto?**

### 5. Lo que no forma parte de la obra

Si el presupuesto incluye algo que no es obra, como un electrodoméstico que solo se vende, sin instalarlo, emitimos dos facturas: la obra al 10 % y lo demás al 21 %. **¿Es correcto separarlo así? ¿Hay algún caso habitual en estos oficios que debamos tratar distinto?**

### 6. Real Decreto-ley 29/2026: pago por banco

Su art. 7 condiciona el 10 % a que la obra se pague con tarjeta, transferencia, cheque nominativo o ingreso en cuenta, y lo amplía a viviendas alquiladas como vivienda habitual. A 11 de noviembre de 2026 no nos consta su convalidación.

**¿Está en vigor? ¿Desde qué fecha se aplica el requisito? ¿Un solo cobro en efectivo hace perder el 10 % a toda la obra?**

## Dos preguntas aparte sobre VERI*FACTU

### El aplazamiento

El 5 de octubre de 2026, Hacienda publicó una nota informativa con la previsión de aplazar a octubre de 2028 «las obligaciones pendientes de aplicación» del Real Decreto 1007/2023 para empresarios y profesionales. A 11 de noviembre de 2026 no nos consta ninguna norma en el BOE.

Nosotros somos productores del programa, y nuestra obligación de ofrecer un sistema adaptado es exigible desde el 29 de julio de 2025. Entendemos que el aplazamiento no nos afecta: el programa debe cumplir el reglamento y llevar declaración responsable desde el primer día, aunque nuestros clientes no estén obligados a usarlo hasta 2028.

**¿Es correcto? ¿Puede un autónomo enviar sus registros a la AEAT de forma voluntaria antes de esa fecha?**

### El importe total que se comunica a la AEAT

El registro de cada factura lleva un campo de importe total. Entendemos que es la base más la cuota de IVA, sin restar la retención de IRPF ni la garantía retenida.

Ejemplo: base de 10.000 € al 21 %, con retención de IRPF del 15 %. Importe total comunicado: 12.100 €. Importe a cobrar: 10.600 €.

**¿Es correcto?**

## Qué haremos con la respuesta

Cada regla se convierte en un cálculo y en una prueba automática del programa. Si alguna depende de un dato que no hemos dado, indíquenos cuál y se lo enviamos.

Antes de lanzar le pediremos además una revisión de facturas de ejemplo ya generadas por el programa.

Muchas gracias. Un cordial saludo,

Borja Peón
KodigoLab
