# ADR-033 — Facturación por fases y trabajos adicionales

- **Estado:** Propuesto
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-PR-07, RF-FA-03, RF-FA-04, RF-FA-05, RF-FA-06, RF-FA-10, RF-FA-11, RF-FA-12, RF-FA-14, RF-FA-15, RN-F-02, RN-F-03, RN-F-10, RN-F-11, RN-F-12, RN-F-13 (historias HU-05, HU-06, HU-07, HU-08 y HU-21)
- **Se cierra en:** Bloque 8

> Este ADR describe cómo modela Kapataz la facturación por fases. No es asesoramiento fiscal. Ningún cliente real emite facturas hasta cerrar el Bloque 12, con la validación de un asesor fiscal (§1, condición legal de lanzamiento).

## Contexto

En las reformas, el autónomo cobra un anticipo antes de empezar para no adelantar el dinero del material, factura la obra por partes y cobra el resto al terminar (HU-06). Durante la obra el cliente pide trabajos que no estaban en el presupuesto (HU-07). A veces se hace menos de lo presupuestado. Y en algunas obras se retiene una parte como garantía hasta una fecha (HU-21).

Cada fase es una factura emitida: inmutable (RN-F-02), con número correlativo (RN-F-01) y con su registro encadenado (RN-F-07). Un error no se corrige editando, sino con una rectificativa (RF-FA-04, RN-F-03).

El tipo de IVA complica todo. Una reforma de vivienda puede ir al 10 % o al 21 % según quién es el destinatario, la antigüedad de la vivienda y el peso del material (RN-F-13). Si se equivoca, el autónomo tiene un problema con Hacienda o con el cliente (HU-08).

En noviembre de 2026 se consultó a dos asesores. Coincidieron en lo principal, pero no en todo: uno propuso una factura final negativa cuando lo facturado supera lo hecho, y uno indicó el 21 % para el anticipo. El plan se aparta de esas dos respuestas, apoyándose en la Ley del IVA, el RD 1619/2012 y consultas de la DGT. Por eso este ADR queda en «Propuesto» hasta tener confirmación por escrito.

## Opciones consideradas

**A. Cómo se calcula cada fase**

1. **Fases como porcentajes del presupuesto** (cada fase factura un porcentaje de cada línea).
   - Ventajas: la suma cuadra siempre con el presupuesto; fácil de calcular.
   - Inconvenientes: el anticipo no responde a un porcentaje de líneas, sino a lo que el cliente paga; no refleja los trabajos realmente hechos ni los adicionales.
2. **Anticipo por importe cobrado; certificación y final por trabajos realizados; la final resta las bases anteriores.**
   - Ventajas: sigue el devengo del IVA en los anticipos (art. 75.Dos de la Ley del IVA) y lo que se ha hecho de verdad; admite diferencias con el presupuesto.
   - Inconvenientes: la suma de las fases solo cuadra con el presupuesto si no se cambia nada; hay que controlar lo facturado y lo pendiente.

**B. Qué hacer cuando lo facturado supera el servicio prestado**

1. **Factura final con base negativa** (lo que propuso un asesor).
   - Ventajas: un solo documento más.
   - Inconvenientes: corrige facturas anteriores sin ser rectificativa.
2. **Factura rectificativa por la diferencia** (art. 80.Dos de la Ley del IVA y art. 15 del RD 1619/2012).
   - Ventajas: es el cauce para modificar la base de facturas ya emitidas; encaja con RN-F-03 y con el registro de la AEAT.
   - Inconvenientes: puede rectificar varias facturas a la vez; hay que confirmar su clase.

**C. Tipo de IVA del anticipo y del material**

1. **Anticipo al 21 % y material por separado** (lo que indicó un asesor).
   - Ventajas: prudente ante la duda.
   - Inconvenientes: contradice que el anticipo lleve el tipo de la operación que paga y que el material forme parte de la obra (arts. 90.Dos y 91.Uno.2.10º de la Ley del IVA; consultas de la DGT V2662-13, V1392-26 y V0624-23).
2. **Un solo tipo para la obra entera, anticipo incluido.**
   - Ventajas: coherente con esas consultas; una sola regla para todas las fases.
   - Inconvenientes: si el material supera el 40 % al final, lo ya facturado al 10 % no se puede rectificar al alza a un particular.

**D. Trabajos que no estaban en el presupuesto**

1. **Crear una nueva versión del presupuesto antes de facturar.**
   - Ventajas: factura y presupuesto coinciden siempre.
   - Inconvenientes: trabajo extra para el autónomo en cada cambio; el presupuesto deja de reflejar lo que se aceptó.
2. **La factura se edita libremente y las líneas añadidas se marcan en la app como trabajo adicional.**
   - Ventajas: refleja la realidad de la obra; el presupuesto queda como referencia.
   - Inconvenientes: hay que avisar cuando se supera lo pendiente para no facturar dos veces lo mismo.

**E. Líneas a tipos de IVA distintos**

1. **Una factura con varios tipos.**
   - Ventajas: un solo documento para el cliente.
   - Inconvenientes: mezcla la obra con lo que no forma parte de ella y complica el cálculo del 40 %.
2. **Una factura por tipo.**
   - Ventajas: cada factura lleva un solo tipo; la obra queda separada de lo que solo se vende.
   - Inconvenientes: dos facturas para el cliente.

## Decisión

Propuesta: A2, B2, C2, D2 y E2, tal como recogen RF-FA-10 a RF-FA-12, RF-FA-15 y RN-F-11 a RN-F-13.

**Fases (RF-FA-10, RN-F-12)**

- Un presupuesto aceptado se puede facturar de una vez o por fases: anticipo, certificación de obra y final (`phase_type`: `full`, `advance`, `progress`, `final`).
- Cada fase es una factura completa, con su número, su IVA y su retención, y lleva el tipo de la obra (RN-F-13).
- El anticipo se factura al cobrarlo, por el importe recibido, porque ahí se devenga el IVA (art. 75.Dos de la Ley del IVA). Con 6.000 € cobrados para una obra al 10 %, la base es 6.000 / 1,10 = 5.454,55 € y la cuota, 6.000 − 5.454,55 = 545,45 € (excepción de RN-03): se redondea la base y la cuota es la diferencia, para que el total coincida al céntimo con lo cobrado.
- La certificación desglosa los trabajos realizados.
- La fase final recoge todos los trabajos realizados, presupuestados o no, resta las bases de las facturas anteriores citándolas (líneas con `origin` = `prior_invoice`) y aplica el IVA al resultado. Con 10.000 € de servicio y 7.000 € ya facturados, la base es 3.000 €.
- Si lo facturado supera el servicio, no se emite una final negativa. Se emite una rectificativa por la diferencia, que rectifica la última fase emitida y, si su importe no basta, también las anteriores, y que detalla lo que se ha quitado del presupuesto (art. 80.Dos de la Ley del IVA y art. 15 del RD 1619/2012). La relación con cada factura rectificada va en `invoice_corrections` (RN-F-03).
- La suma de las fases no tiene que coincidir con el presupuesto: solo cuadra al céntimo si no se cambia nada.
- Al emitir la factura completa o la fase final, el presupuesto queda «facturado» aunque haya diferencia.

**Control de lo facturado (RF-FA-11, RN-F-11)**

- El presupuesto muestra lo facturado, lo pendiente y la diferencia con lo presupuestado, con enlace a cada factura.
- El presupuesto es una referencia, no un tope: lo facturado puede ser mayor o menor.
- Si una factura supera lo pendiente, la app avisa de la diferencia y pide confirmarla, también cuando la propone el agente (ADR-018).
- Un borrador cuenta como facturado hasta que se elimina, y una rectificativa ajusta lo facturado.

**Trabajos adicionales (RF-FA-12)**

- Una factura creada desde un presupuesto se puede cambiar: añadir trabajos no presupuestados, cambiar líneas o quitarlas, sin crear una nueva versión del presupuesto.
- Las líneas añadidas quedan marcadas en la app como trabajo adicional (`AdditionalWork`, `origin` = `additional`). La factura no las distingue, porque recoge todos los trabajos realizados.
- Una factura se vincula, como mucho, a un presupuesto.

**Tipo de IVA de la obra (RN-F-13)**

- El tipo se decide para la obra entera, no por línea: material, mano de obra y anticipos llevan el mismo (arts. 90.Dos y 91.Uno.2.10º de la Ley del IVA; consultas V2662-13, V1392-26 y V0624-23).
- Va al 10 % si el destinatario es una persona física que usa la vivienda para fines particulares o una comunidad de propietarios, la vivienda se terminó al menos dos años antes de empezar la obra y el material que aporta el autónomo no supera el 40 % de la base. Si no, al 21 %.
- La app pide los dos primeros datos en el presupuesto, o en la factura si no sale de un presupuesto (`recipient_type`, `dwelling_over_two_years`), y calcula el 40 % con las líneas marcadas como material (`is_material`).
- La app avisa antes de facturar al 10 % cuando el material llega al 35 % de la base.
- Si al final el material supera el 40 %, toda la obra pasa al 21 %. Lo ya facturado al 10 % a un particular no se rectifica al alza: el autónomo ingresa la diferencia (art. 89.Tres y Cinco de la Ley del IVA; consulta V0624-23). La fase final va al 21 % y la app muestra el IVA que debe ingresar por lo ya facturado al 10 %.
- Real Decreto-ley 29/2026: para el 10 % exige que la obra se pague con tarjeta, transferencia, cheque nominativo o ingreso en cuenta, y lo extiende a viviendas alquiladas como vivienda habitual. La app registra la forma de cada cobro (`payments.method`) y avisa si es en efectivo.
- Lo que no forma parte de la obra, como muebles o electrodomésticos que solo se venden sin instalarlos, va al 21 % (`outside_works`). Al facturar un presupuesto con líneas de los dos tipos, la app genera dos facturas.
- Regla general: una factura emitida por la app lleva un solo tipo de IVA, y un borrador con líneas a tipos distintos genera una factura por tipo. El histórico importado conserva sus facturas como son.

**Garantía (RF-FA-15)**

- Al emitir la factura completa o la fase final, el usuario puede retener como garantía (`Guarantee`) un porcentaje de la base imponible, con su vencimiento (`guarantee_pct`, `guarantee_amount`, `guarantee_due_date`). No es la retención de IRPF (`Withholding`).
- La factura lleva el importe total con su IVA y dice cuánto se retiene y hasta cuándo. `total_amount` es base más cuota; `amount_due` es lo que se cobra ahora.
- El importe retenido queda pendiente de cobro con su fecha y entra en los avisos de vencidas (RF-FA-14).
- No se admite en anticipos ni en certificaciones, donde la base sería solo lo cobrado (consultas V0846-07 y V0053-13). Se apoya en la consulta V0942-16, leída en fuentes secundarias.

**Dónde vive cada regla:** el cálculo de fases, del 40 % y de la garantía va en el dominio (`billing`), como funciones puras sobre `Decimal` (RN-01 a RN-03, con la excepción de RN-03 para el anticipo, ADR-009). El LLM nunca calcula importes (RN-02).

### Escenarios (copiados de §3.5)

```gherkin
Escenario: Factura por fases sin cambios sobre el presupuesto
  Dado un presupuesto aceptado de 10.000,00 € de base, todo al 21 %
  Cuando facturo un anticipo cobrado de 3.630,00 €, una certificación de los trabajos hechos por 4.000,00 € de base y la fase final
  Entonces existen tres facturas con número propio y con su IVA
  Y el anticipo tiene una base de 3.000,00 €
  Y la factura final muestra 10.000,00 € de servicio, resta 7.000,00 € y tiene una base de 3.000,00 €
  Y la suma de sus bases es exactamente 10.000,00 €
  Y el presupuesto queda "facturado"

Escenario: Anticipo antes de empezar la obra
  Dado un presupuesto aceptado de una reforma que cumple los requisitos del 10 %
  Cuando el cliente paga 6.000,00 € antes de empezar la obra
  Entonces la factura de anticipo es de 6.000,00 € al 10 %
  Y tiene una base de 5.454,55 € y una cuota de 545,45 €

Escenario: Presupuesto con líneas a dos tipos de IVA
  Dado un presupuesto aceptado de una reforma al 10 % de 8.000,00 € de base
  Y una línea de 600,00 € por un electrodoméstico que solo se vende, al 21 %
  Cuando lo facturo
  Entonces se generan dos facturas
  Y una tiene 8.000,00 € de base al 10 % y la otra, 600,00 € al 21 %

Escenario: El material supera el 40 % de la base
  Dado una reforma de 5.000,00 € de base con 2.500,00 € de material
  Cuando preparo la factura
  Entonces la app aplica el 21 % a toda la obra y explica el motivo

Escenario: Material cerca del límite del 40 %
  Dado una reforma al 10 % de 5.000,00 € de base con 1.800,00 € de material
  Cuando preparo la factura
  Entonces la app avisa de que el material es el 36 % de la base y el límite es el 40 %
  Y mantiene el 10 %

Escenario: El material supera el 40 % con un anticipo ya facturado al 10 %
  Dado una reforma con un anticipo facturado de 1.000,00 € de base al 10 %
  Cuando preparo la fase final y el material supera el 40 % de la base
  Entonces la fase final va al 21 %
  Y la app no rectifica el anticipo
  Y me avisa de que debo ingresar 110,00 € de IVA por la diferencia

Escenario: Cobro en efectivo de una obra al 10 %
  Dado una reforma facturada al 10 %
  Cuando registro un cobro en efectivo
  Entonces la app avisa de que el 10 % exige el pago por tarjeta, transferencia, cheque nominativo o ingreso en cuenta

Escenario: Trabajo adicional en la misma factura
  Dado un presupuesto aceptado de 6.000,00 € de base por hacer el suelo de una casa
  Cuando lo convierto en factura y añado 3.000,00 € por reformar los baños
  Entonces la app avisa "Esta factura supera lo presupuestado en 3.000,00 €"
  Y al confirmar se emite una sola factura de 9.000,00 € de base
  Y las líneas de los baños quedan marcadas en la app como trabajo adicional, pero no en la factura
  Y el presupuesto queda "facturado" con una diferencia de 3.000,00 €

Escenario: Fase superior a lo pendiente
  Dado un presupuesto de 10.000,00 € con 7.000,00 € facturados
  Cuando preparo una fase de 4.000,00 €
  Entonces la app avisa "Quedan 3.000,00 € por facturar; esta fase lo supera en 1.000,00 €"
  Y la factura solo se emite si lo confirmo

Escenario: Se factura menos de lo presupuestado
  Dado un presupuesto de 10.000,00 € con 7.000,00 € facturados
  Cuando emito la fase final por un servicio prestado de 9.000,00 €
  Entonces la factura resta los 7.000,00 € y tiene una base de 2.000,00 €
  Y el presupuesto queda "facturado" con una diferencia de -1.000,00 €

Escenario: Se ha facturado más de lo que se ha hecho
  Dado un presupuesto de 10.000,00 € con 7.000,00 € facturados
  Cuando preparo la fase final por un servicio prestado de 6.000,00 €
  Entonces la app no emite una factura final con base negativa
  Y propone una factura rectificativa de -1.000,00 € de base sobre la última fase emitida
  Y la rectificativa detalla los trabajos del presupuesto que no se han hecho

Escenario: Retención de garantía en la factura final
  Dado una fase final de 10.000,00 € de base al 21 %
  Cuando la emito con un 5 % de garantía a 12 meses
  Entonces la factura tiene un total de 12.100,00 € e indica 500,00 € retenidos y hasta cuándo
  Y quedan 500,00 € pendientes de cobro con vencimiento a 12 meses
```

## Consecuencias

- **Positivas:**
  - Las facturas reflejan lo cobrado y lo hecho, no un reparto teórico del presupuesto.
  - El autónomo ve en todo momento lo facturado, lo pendiente y la diferencia.
  - Una sola regla de IVA para toda la obra, con avisos antes de equivocarse.
  - Las correcciones van siempre por rectificativa, coherente con la inmutabilidad y con Verifactu.
- **Negativas y mitigación:**
  - Más estados y cálculos en el dominio. Se mitiga con funciones puras, pruebas de propiedades y mutación sobre `domain/billing`.
  - Si el material supera el 40 % al final, el autónomo debe ingresar IVA que no cobró al cliente. La app no lo evita, pero avisa desde el 35 % y muestra el importe a ingresar.
  - Dos facturas cuando hay líneas fuera de la obra. Se explica en la pantalla de facturación.
  - Varias decisiones dependen de criterios fiscales aún no confirmados por escrito. Por eso el ADR sigue en «Propuesto» y ninguna factura real se emite antes del Bloque 12.
- **Qué haría reconsiderarla:** que un asesor fiscal confirme por escrito un criterio distinto en cualquiera de los puntos pendientes, un cambio normativo (en especial sobre el Real Decreto-ley 29/2026) o una nueva consulta de la DGT que cambie el tratamiento del anticipo, del material o de la garantía.

## Pendiente para cerrar

Antes de cerrar este ADR en el Bloque 8 hay que confirmar por escrito con un asesor fiscal:

1. **Tipo de IVA del anticipo.** Dos asesores dieron respuestas distintas. El plan sigue las consultas de la DGT V2662-13, V1392-26 y V0624-23: el anticipo lleva el tipo de la obra.
2. **Material que supera el 40 % al final.** Confirmar que la fase final pasa al 21 %, que lo facturado al 10 % a un particular no se rectifica al alza y que el autónomo ingresa la diferencia (art. 89.Tres y Cinco de la Ley del IVA; consulta V0624-23). Falta saber cómo se declara esa diferencia y qué debe mostrar la app para que el autónomo o su gestoría la declaren.
3. **Rectificativa frente a factura final negativa.** Confirmar la rectificativa por la diferencia (art. 80.Dos de la Ley del IVA y art. 15 del RD 1619/2012) y si corresponde la clase R1 cuando rectifica varias facturas a la vez (RN-F-03).
4. **Retención de garantía.** Confirmar el tratamiento de la consulta V0942-16, que solo se ha leído en fuentes secundarias: base completa al entregar la obra, IVA devengado al pagar o al poner la obra a disposición, y garantía solo en la factura completa o en la fase final.
5. **Separación en dos facturas de lo que no es obra.** Confirmar que lo que solo se vende, sin instalar, va en una segunda factura al 21 %, y qué líneas cuentan como fuera de la obra.
6. **Real Decreto-ley 29/2026 (pago por banco).** Confirmar su convalidación, desde cuándo se aplica y su alcance. A 11 de noviembre de 2026 seguía sin votarse. Afecta a los cobros del Bloque 8 y hay que resolverlo antes de ese bloque. Incluye cómo se recoge la vivienda alquilada como vivienda habitual, porque `recipient_type` solo admite `private`, `community` y `business`.

Decisiones de diseño que se cierran a la vez, con los datos anteriores:

- Sobre qué base se calcula el 40 % cuando hay líneas `outside_works`, y en qué momento se evalúa en una obra por fases (el anticipo no tiene líneas).
- Cómo se presenta en la app el IVA que el autónomo debe ingresar por lo facturado al 10 %.

## Verificación

- Los doce escenarios de arriba automatizados en el Bloque 8 a través de la API y en verde, con su marcador: `@pytest.mark.req("RN-F-12")` para fases y rectificativa, `req("RN-F-13")` para el tipo de IVA y el cobro en efectivo, `req("RN-F-11")` y `req("RF-FA-12")` para lo pendiente y los trabajos adicionales, y `req("RF-FA-15")` para la garantía.
- Prueba de propiedades con hypothesis: sin trabajos adicionales, la suma de las fases cuadra al céntimo con el presupuesto para cualquier reparto; la suma de bases y cuotas cuadra con el total (RN-03).
- Prueba de que una factura emitida lleva un solo tipo de IVA y de que un borrador con dos tipos genera dos facturas (`req("RN-F-13")`).
- Prueba de rectificativa de varias facturas: guarda la referencia a todas, su clase y su tipo (`req("RN-F-03")`).
- Prueba de total y cobro: con retención de IRPF y con garantía, `total_amount` es base más cuota y `amount_due` es menor.
- Aviso al superar lo pendiente también cuando propone el agente; dos borradores a la vez cuentan; eliminar un borrador libera su importe (`req("RN-F-11")`).
- Mutación con mutmut sobre `domain/billing` con puntuación de al menos el 80 %, y cobertura de `domain/` de al menos el 90 %.
- Validación fiscal de un asesor antes del lanzamiento (Bloque 12).
