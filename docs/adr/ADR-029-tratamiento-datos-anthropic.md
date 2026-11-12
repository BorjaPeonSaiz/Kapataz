# ADR-029 — Tratamiento de datos con Anthropic

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-11, RNF-01, RNF-17. ADR relacionados: ADR-005 (Claude como LLM), ADR-010 (el PDF no sale hacia Claude), ADR-011 (el audio no sale hacia terceros), ADR-030 (seudonimización antes de Claude).

## Contexto

Kapataz usa la API de Claude para el chat, la clasificación y la extracción (ADR-005). Cada autónomo es responsable del tratamiento de los datos de sus clientes y proveedores. KodigoLab es su encargado. Si Anthropic recibe esos datos, es nuestro subencargado.

Antes de enviar nada a Claude, el servidor sustituye por seudónimos los nombres, NIF, direcciones y datos de contacto (RN-11, ADR-030). A Claude solo llega texto: nunca un PDF, una imagen ni un audio. La tabla de equivalencias se queda en nuestro servidor.

La seudonimización no es perfecta. RNF-17 exige 0 NIF, emails, teléfonos, IBAN y nombres de clientes registrados, pero acepta que se escape hasta un 2 % de los nombres no registrados. Además, KodigoLab conserva la tabla de equivalencias, así que puede reidentificar.

Fuerzas en juego:

- RNF-01 promete datos en servidores de la UE y que Anthropic solo recibe texto seudonimizado. El usuario debe saberlo antes de usar la IA.
- Anthropic almacena los datos en Estados Unidos y no ofrece tratamiento solo en la UE.
- Anthropic no está adherida al Marco de Privacidad de Datos UE-EE. UU.
- Debemos nombrar a los subencargados en los contratos con los autónomos y avisarles de los cambios a tiempo.

## Opciones consideradas

1. **Anthropic como subencargado, con seudonimización previa.** Se trata lo enviado como dato personal. Se firma su contrato de tratamiento, con cláusulas contractuales tipo, y se hace una evaluación de impacto de la transferencia.
   - Ventajas: cubre el riesgo residual de la seudonimización. Es la lectura prudente del considerando 26 del RGPD. Es coherente con lo que prometemos al usuario.
   - Inconvenientes: más papeleo (lista de subencargados, avisos, evaluación de la transferencia). Dependemos de que Anthropic nos dé la información para esa evaluación.

2. **No tratar a Anthropic como subencargado, porque solo recibe datos seudonimizados.**
   - Ventajas: menos obligaciones contractuales y sin evaluación de la transferencia.
   - Inconvenientes: el considerando 26 dice que los datos seudonimizados siguen siendo datos personales. La sentencia del TJUE de 4 de septiembre de 2025 (C-413/23 P, SRB) admite que pueden no serlo para un destinatario sin medios razonables de reidentificar. Pero esa valoración es caso por caso, y para quien envía, que conserva la tabla, siguen siendo personales. Además, nuestra seudonimización deja pasar algunos nombres (RNF-17). Si un abogado o la AEPD no aceptan esta lectura, todo el tratamiento queda sin cobertura. Se descarta.

3. **Un modelo autoalojado en nuestro servidor de la UE.**
   - Ventajas: ningún dato sale de nuestros servidores. Sin transferencia internacional ni subencargado de IA.
   - Inconvenientes: peor calidad en tool use y extracción que Claude (ADR-005). Exige GPU y operación que un VPS sencillo no da (ADR-014). Más coste y más trabajo para un proyecto de una persona. Se descarta para la v1. `LlmPort` permite reconsiderarlo sin tocar el dominio.

## Decisión

Se elige la **opción 1**.

- Anthropic es subencargado aunque reciba datos seudonimizados, porque siguen siendo datos personales (considerando 26 del RGPD).
- La entidad que contrata con clientes del Espacio Económico Europeo es **Anthropic Ireland, Limited**. Es la que se nombra como subencargado en los contratos con los autónomos.
- El contrato de tratamiento de Anthropic forma parte de sus condiciones comerciales. Incluye cláusulas contractuales tipo, módulos 2 y 3, regidas por la ley irlandesa. Su soporte confirmó por escrito, en noviembre de 2026, que el módulo 3 cubre nuestro papel de encargado.
- Anthropic no está adherida al Marco de Privacidad UE-EE. UU. Su soporte lo confirmó por escrito en noviembre de 2026. La transferencia a Estados Unidos se apoya solo en las cláusulas tipo, más una evaluación de impacto de la transferencia.
- Retención de la API: entradas y salidas se borran en 30 días. Lo marcado por seguridad se guarda hasta 2 años, y las puntuaciones de clasificación, hasta 7. Se pedirá la retención cero.
- Los datos se almacenan en Estados Unidos. No hay tratamiento solo en la UE: `inference_geo` admite `us` y `global`.
- Solo se usa la Messages API. Ni Files API, ni Batch API, ni ejecución de código: guardan datos aunque haya retención cero.

Nada de esto cambia el principio de RN-11: si la seudonimización falla, la petición no se envía.

## Consecuencias

**Positivas**

- El tratamiento queda cubierto aunque se escape algún dato personal.
- Los contratos con los autónomos nombran a un subencargado concreto, con su base de transferencia.
- Lo que contamos al usuario (RNF-01) coincide con lo que pasa de verdad.

**Negativas y cómo se mitigan**

- Los datos van a Estados Unidos sin decisión de adecuación para Anthropic. Mitigación: seudonimización previa (ADR-030), solo texto, cláusulas tipo, evaluación de la transferencia y retención cero.
- Hasta 30 días de retención mientras no haya retención cero, y hasta 2 años si algo se marca por seguridad, incluso con retención cero. Mitigación: lo que se marca ya está seudonimizado. Se explica en la política de privacidad.
- El contrato de tratamiento da 15 días para oponerse a un subencargado nuevo, pero no fija el canal del aviso. Mitigación: suscribirse al canal de novedades del centro de confianza de Anthropic y mantener al día el email de la cuenta de la API, hasta que su equipo de privacidad confirme el canal. Nuestro plazo para avisar a los autónomos debe caber dentro de esos 15 días.
- Con salidas estructuradas o herramientas con `strict: true`, Anthropic guarda el esquema JSON hasta 24 horas, también con retención cero. Mitigación: los esquemas de herramientas son fijos y nunca llevan datos de clientes.
- Dependemos de que Anthropic nos dé la información para la evaluación de la transferencia. Mitigación: no se usan datos reales hasta tenerla (ver «Pendiente antes de usar datos reales»).

**Qué haría reconsiderar esta decisión**

- Que Anthropic ofrezca almacenamiento o inferencia solo en la UE.
- Que Anthropic se adhiera al Marco de Privacidad, o que este caiga.
- Que la retención cero no se conceda.
- Que el superadministrador quiera usar un «Covered Model» (Claude Fable o Claude Mythos): exigen 30 días de retención y no admiten retención cero salvo autorización expresa de Anthropic. `claude-opus-5-5` no está en esa lista.
- Que el abogado o la AEPD lean de otra forma el carácter personal de los datos seudonimizados.
- Que un modelo autoalojado alcance la calidad necesaria a un coste asumible.

## Verificación

- **Puerta única hacia Claude:** import-linter impide importar el SDK de Anthropic fuera del adaptador de infraestructura. `LlmPort` solo acepta `SanitizedPrompt` (ADR-030).
- **Prueba de fuga:** `test_llm02_payload_sin_datos_personales` captura lo que llega a `LlmPort` y comprueba RNF-17.
- **Solo Messages API:** una prueba del adaptador comprueba que no usa Files API, Batch API ni herramientas de ejecución de código.
- **Solo texto:** una prueba comprueba que ninguna petición lleva bloques de documento, imagen o audio (ADR-010, ADR-011).
- **Esquemas sin datos personales:** los esquemas de las herramientas son constantes del código y se revisan en el PR.
- **Pre-release:** la casilla «Condiciones de Anthropic (ADR-029)» de `docs/plan-verificacion-kapataz.md` vuelve a contrastar este ADR con las condiciones vigentes.

## Contraste con las condiciones vigentes (12/11/2026)

Leyenda: **Confirmado**, **Cambiado** (dato nuevo o matiz) o **No verificable** con fuentes públicas.

| Dato | Qué dice el plan | Qué dicen las fuentes | Fuente (URL) |
|---|---|---|---|
| Entidad contratante en el EEE | Anthropic Ireland, Limited | **Confirmado.** Anthropic Ireland, Limited para clientes del EEE, Suiza y Reino Unido; Anthropic, PBC para el resto. Condiciones comerciales vigentes desde el 17/06/2025 | https://www.anthropic.com/legal/commercial-terms |
| Contrato de tratamiento | Incluido en las condiciones comerciales | **Confirmado.** Se incorpora por referencia (sección C). Versión vigente desde el 24/02/2025 | https://www.anthropic.com/legal/commercial-terms y https://www.anthropic.com/legal/data-processing-addendum |
| Cláusulas tipo | Módulos 2 y 3 | **Confirmado.** Sección I.1: módulo 2 y/o módulo 3. La cobertura del módulo 3 para nuestro papel la confirmó el soporte por escrito | https://www.anthropic.com/legal/data-processing-addendum |
| Ley de las cláusulas | Ley irlandesa | **Confirmado.** Anexo 3, A.1.c (cláusula 17, opción 1) y A.1.d (foro en Irlanda) | https://www.anthropic.com/legal/data-processing-addendum |
| Importador de datos | Anthropic Ireland | **Confirmado** de forma indirecta: el importador es «la entidad de Anthropic que firmó el contrato» (anexo 1, A.2) | https://www.anthropic.com/legal/data-processing-addendum |
| Transferencia de Anthropic Ireland a Anthropic, PBC | Se apoya en las cláusulas tipo | **No verificable.** El contrato de tratamiento no regula la transferencia dentro del grupo. Es lo que se pidió por la sección I.4 | https://www.anthropic.com/legal/data-processing-addendum |
| Información para la evaluación de la transferencia | Pedirla | **Confirmado.** Sección I.4: Anthropic da, a petición, la información razonablemente necesaria | https://www.anthropic.com/legal/data-processing-addendum |
| Marco de Privacidad UE-EE. UU. | Anthropic no está adherida | **No verificable** en la lista oficial: es una página dinámica. Ni la política de privacidad (10/09/2026) ni el contrato de tratamiento lo mencionan; la política cita cláusulas tipo y decisiones de adecuación. Algunas webs de terceros dicen lo contrario, sin fuente oficial. Vale la confirmación escrita del soporte | https://www.anthropic.com/legal/privacy y https://www.dataprivacyframework.gov/list |
| Retención estándar de la API | 30 días | **Confirmado.** Artículo actualizado el 01/07/2026 | https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data |
| Contenido marcado por seguridad | Hasta 2 años; puntuaciones, hasta 7 | **Confirmado.** Además, se aplica también con retención cero, y se puede retener lo que exija la ley | https://platform.claude.com/docs/en/manage-claude/api-and-data-retention |
| Retención cero | Pedirla al equipo de ventas; se concede por organización | **Confirmado.** Se pide a ventas y se activa por organización. **Matiz nuevo:** los «Covered Models» (Claude Fable y Claude Mythos) exigen 30 días y no admiten retención cero; `claude-opus-5-5` sí la admite | https://platform.claude.com/docs/en/manage-claude/api-and-data-retention |
| Funciones fuera de la retención cero | Sin Files API | **Confirmado.** Files API, Batch API y ejecución de código quedan fuera. **Matiz nuevo:** con salidas estructuradas o `strict: true` se guarda el esquema JSON hasta 24 horas | https://platform.claude.com/docs/en/manage-claude/api-and-data-retention |
| Región de inferencia | `inference_geo` admite `us` y `global` | **Confirmado.** Disponible para `claude-opus-5-5`. **Matiz nuevo:** `us` cuesta 1,1 veces la tarifa estándar; con `global`, el tráfico puede ir a Estados Unidos, Europa, Asia y Australia | https://platform.claude.com/docs/en/manage-claude/data-residency y https://privacy.claude.com/en/articles/7996890-where-are-your-servers-located-do-you-host-your-models-on-eu-servers |
| Almacenamiento | En Estados Unidos; no hay tratamiento solo en la UE | **Confirmado.** La geografía del espacio de trabajo solo admite `us` y no se puede cambiar | https://platform.claude.com/docs/en/manage-claude/data-residency |
| No entrenamiento | Anthropic no entrena con nuestros datos | **Confirmado.** Condiciones comerciales, sección B | https://www.anthropic.com/legal/commercial-terms |
| Aviso de subencargados nuevos | 15 días para oponerse; canal sin confirmar | **Confirmado.** Sección C.3: aviso razonable y 15 días; no fija el canal. Las condiciones comerciales (M.2) permiten comunicar por email, por el panel o publicando en su web | https://www.anthropic.com/legal/data-processing-addendum y https://www.anthropic.com/legal/commercial-terms |
| Lista de subencargados | En el centro de confianza | **No verificable** automáticamente: la página es dinámica. El contrato de tratamiento remite a `anthropic.com/subprocessors`, que redirige al centro de confianza. Hay que revisarla a mano | https://trust.anthropic.com/subprocessors |
| Borrado al terminar el contrato | No lo recoge el plan | **Dato nuevo.** Sección H.1: devolución o borrado en 30 días desde el fin del contrato, salvo obligación legal, disputa o uso dañino | https://www.anthropic.com/legal/data-processing-addendum |

Ningún dato contradice la decisión. Los matices nuevos se recogen en «Consecuencias».

## Pendiente antes de usar datos reales

- [ ] **Retención cero:** solicitada al equipo de ventas en noviembre de 2026. Sin respuesta.
- [ ] **Canal de aviso de subencargados nuevos:** a confirmar con su equipo de privacidad. Mientras tanto, suscribirse al canal de novedades del centro de confianza y mantener al día el email de la cuenta.
- [ ] **Información para la evaluación de impacto de la transferencia** (sección I.4 del contrato de tratamiento): solicitada. Debe aclarar cómo se cubre la transferencia de Anthropic Ireland a Anthropic, PBC.
- [ ] **Cuenta de la API:** crearla con el email de la empresa. No se puede cambiar después, y la retención cero se concede a esa organización concreta.
- [x] **Condiciones:** Borja revisó y aceptó el 12/11/2026 las condiciones comerciales y el contrato de tratamiento tal como se contrastan en este ADR, incluidas dos novedades frente al plan: Claude Fable y Mythos no admiten retención cero, y al terminar el contrato Anthropic devuelve o borra los datos en 30 días. Al crear la cuenta de la API se acepta la versión vigente; si ha cambiado desde esa fecha, se vuelve a revisar.
- [ ] **Lista de subencargados:** revisarla a mano en el centro de confianza y guardar una copia con fecha.
- [ ] **Revisión del abogado:** contrato de encargo con los autónomos, lista de subencargados, evaluación de la transferencia y lectura del carácter personal de los datos seudonimizados. Guardar las respuestas escritas del soporte como prueba.
