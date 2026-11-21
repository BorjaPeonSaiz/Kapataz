# ADR-020 — Datos sintéticos para demo y pruebas

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Modificado:** 2026-11-20. Al cerrar el Bloque 3, Borja aprueba que los PDF vayan solo en `samples/`, que `seed_demo.py` no emita facturas y que la marca de RN-F-09 no se aplique a los PDF del histórico sintético. Con las correcciones de las revisiones de cierre, aprueba además que la app no use Faker, los datos de contacto no atribuibles, `may_flag_for_review` y la carga de los presupuestos facturados (decisiones 7 a 10 de «Cierre en el Bloque 3»).
- **Modificado:** 2026-11-21. Borja aprueba las correcciones de la segunda revisión de seguridad: teléfonos en el segmento 4 del plan de numeración (S3-R-02, decisión 8) y `content_sha256` sobre el PDF entero con la estructura validada (S3-R-01, «Alcance del determinismo»).
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-CF-04, RN-F-09, RN-13, RN-05, RNF-06, RNF-07, RNF-17, RF-IN-05; al cerrar, también RF-IN-02, RF-IN-03, RF-IN-09 y RN-F-06
- **Se cierra en:** Bloque 3. Cerrado el 20/11/2026 (ver «Cierre en el Bloque 3»).

## Contexto

Kapataz necesita datos para cuatro cosas: la demo pública, el modo demostración de cada cuenta (RF-CF-04), las pruebas automáticas y los datasets de evaluación de la IA (RNF-06, RNF-07, RNF-17). Mientras queden pendientes legales, las cuentas solo trabajan en el espacio de demostración (RN-13).

Esos datos tienen que parecer reales: maquetaciones de PDF distintas, errores típicos, nombres que se repiten, IVA general y reducido, inversión del sujeto pasivo y retenciones. Pero no pueden ser de nadie: usar facturas reales metería datos personales en el repo, en CI y en lo que se envía a Claude.

## Opciones consideradas

1. **Facturas reales anonimizadas** (propias o de conocidos).
   - Ventajas: realismo máximo en maquetación y conceptos.
   - Inconvenientes: datos personales en el repo y en CI; la anonimización manual falla; no se pueden sembrar errores a voluntad ni tener verdad de referencia exacta.
2. **Datos escritos a mano.**
   - Ventajas: control total de cada caso.
   - Inconvenientes: pocos documentos, poca variación y mucho trabajo para 18 meses de actividad.
3. **Datos generados por un LLM.**
   - Ventajas: textos variados con poco esfuerzo.
   - Inconvenientes: no determinista, con coste por ejecución y sin garantía de que las cifras cuadren donde deben cuadrar.
4. **Generador propio con Faker `es_ES` y reglas de oficio, determinista con semilla.**
   - Ventajas: reproducible, sin datos de nadie, con errores sembrados conocidos y con su JSON esperado.
   - Inconvenientes: hay que escribir y mantener el generador y las plantillas de PDF.

## Decisión

Se elige la opción 4.

- `tools/gen_synthetic.py` genera dos profesionales ficticios: un electricista autónomo en Cantabria y un albañil que trabaja para constructoras (inversión del sujeto pasivo, retenciones).
- Cada uno con 18 meses de actividad, 40–60 facturas y 20–30 presupuestos. Clientes particulares, comunidades de vecinos y empresas, con nombres repetidos a propósito para probar la ambigüedad (RF-CO-05).
- Conceptos de oficio con precios coherentes y variación realista.
- Cinco maquetaciones de PDF: tabla clásica, Word exportado, plantilla de programa genérico, texto sin tabla, y con logotipo y pie extensos.
- Imperfecciones sembradas: totales con errores, IVA mal calculado, NIF ausente y líneas partidas entre páginas.
- PDF trampa con instrucciones inyectadas (RN-05, ADR-019).
- Los PDF se versionan solo en `samples/`. Cada uno tiene su JSON esperado, con el mismo nombre, en `evals/extraction/`.
- El generador es determinista con semilla: la misma semilla produce los mismos datos.
- `seed_demo.py` carga el modo demostración. Las facturas que emite la app en el espacio de demostración llevan siempre la marca «Documento de demostración» (RN-F-09). Los PDF sintéticos del histórico no la llevan, porque no los emite la app.

## Consecuencias

- **Positivas:**
  - Ningún dato real en el repo, en CI ni en las evaluaciones con Claude.
  - Verdad de referencia exacta para medir la extracción y las fugas de la seudonimización.
  - La demo se puede regenerar en cualquier momento.
- **Negativas y mitigación:**
  - Los datos sintéticos pueden ser más «limpios» que los reales. Se mitiga con las imperfecciones sembradas y con varias maquetaciones; si la Fase 4 detecta sesgo, se añaden plantillas.
  - Un NIF generado con dígito de control válido puede coincidir con el de una persona real. Se mitiga generándolo siempre junto a nombres ficticios y solo en espacios de demostración y pruebas. Teléfonos, IBAN y correos sí son inatribuibles (decisión 8); el DNI queda como riesgo residual R-16 de `docs/03-modelo-amenazas.md`.
- **Qué haría reconsiderarla:** que la precisión medida con datos sintéticos no se parezca a la que observa Borja con sus propios documentos en pruebas manuales.

## Verificación

- Determinismo del dataset: la misma semilla da el mismo `SyntheticDataset` y otra semilla da otro (`tests/unit/tools/test_synthetic_dataset.py`, `req("RF-CF-04")`).
- Determinismo del render: lo regenerado coincide con lo versionado, los JSON byte a byte y los PDF por `content_sha256`; dos ejecuciones en la misma máquina dan los mismos bytes, también en los escaneados (`tests/unit/tools/test_synthetic_regeneration.py`, sin `req`: verifica el dataset de evaluación, no un requisito de la app).
- Huella y `--check` frente a PDF manipulados (S3-R-01): otra zlib, otro libjpeg y otro nombre de XObject dan la misma huella y `check()` sigue en verde; una actualización incremental, una tabla de referencias reescrita hacia un catálogo nuevo, nombres con escapes `#xx`, un `/Subject` distinto en un escaneado, bytes tras el `%%EOF`, cifrado, filtros no admitidos, un JPEG con comentario o una bomba zlib la rompen o se rechazan (`tests/unit/tools/test_synthetic_fingerprint.py`, sin `req` por lo mismo).
- Sin contenido activo: en ningún PDF de `samples/`, con los escapes `#xx` resueltos y sin saltar ningún flujo, aparecen JavaScript, acciones, adjuntos, formularios, anotaciones, actualizaciones incrementales ni cifrado; además, PDFium no ve JavaScript ni manejador de seguridad (`tests/unit/tools/test_synthetic_truth.py::test_ningun_pdf_lleva_contenido_activo_ni_adjuntos`).
- Completitud: todo PDF de `samples/` tiene su JSON en `evals/extraction/` y todo JSON tiene su PDF; cada JSON valida contra el esquema versionado y el manifiesto cubre cada fichero con su SHA-256 (`tests/unit/tools/test_synthetic_truth.py`).
- Verdad de referencia: sin error sembrado, los importes cuadran con un solo redondeo (RN-03); cada error sembrado rompe solo la cuenta que declara; el NIF ausente no está en el PDF; los escaneados son solo imagen y son el 15 %; los PDF trampa esperan cero acciones (RN-05) (`tests/unit/tools/test_synthetic_truth.py`).
- `gen_synthetic.py --check` en verde contra lo versionado (ver «Alcance del determinismo»).
- Contrato de import-linter «La app no importa el generador sintético de tools/»: nada de `kapataz` importa `synthetic`, `gen_synthetic`, `seed_demo` ni `tools` (`backend/pyproject.toml`). Faker y ReportLab, en el grupo `dev`, no llegan a la imagen (decisión 7).
- Carga de la demo: el espacio se crea con su cuenta padre, carga todo el contenido del dataset, falla sin escribir nada si ya existe y ninguna otra cuenta lo ve (`tests/unit/application/test_load_demo_space.py`, `tests/unit/tools/test_seed_demo.py` y `tests/integration/persistence/test_seed_demo.py`, `req("RF-CF-04")`).
- Escenario «Primer arranque»: se cargan datos de ejemplo en un espacio separado (`req("RF-CF-04")`). Queda para el bloque que lo exponga en la app.
- Escenario «Extracción que no cuadra» sobre un PDF con total erróneo sembrado (`req("RF-IN-05")`). Bloque 4.
- gitleaks en CI. La Fase 7 comprueba que los PDF de `samples/` son sintéticos por sus metadatos (decisión 6).
- Criterio de terminado del Bloque 3: `samples/` y `evals/extraction/` versionados.

## Cierre en el Bloque 3

### Lo construido

- **Generador:** `backend/tools/gen_synthetic.py` y el paquete `backend/tools/synthetic/`. Desde `backend/`:
  - `uv run python tools/gen_synthetic.py` escribe en la raíz del repositorio;
  - `--seed N --out DIR` escribe otra semilla en otra carpeta;
  - `--check` regenera en memoria, compara con lo versionado y sale con 1 si hay diferencias (qué compara, en «Alcance del determinismo»).
- **API pura:** `synthetic.build.build_dataset(seed)` devuelve un `SyntheticDataset` con dataclasses inmutables y `Decimal`, sin E/S y sin reloj. Los tipos están en `synthetic/model.py`, que documenta cómo se traduce cada uno al dominio. La usa `seed_demo.py`.
- **Periodo y semilla:** periodo fijo del 1/1/2025 al 30/6/2026 (18 meses); semilla por defecto 20251120.
- **Salida:**
  - `samples/{electricista,albanil}/doc-NNN.pdf`: los 156 PDF, unos 8,9 MB;
  - `evals/extraction/{electricista,albanil}/doc-NNN.json`: la verdad de referencia de cada PDF, con el mismo nombre;
  - `evals/extraction/extraction.schema.v1.json`: el JSON Schema (draft 2020-12);
  - `evals/extraction/manifest.json`: el manifiesto;
  - `evals/README.md`: avisa de que `evals/` y `samples/` son dato no confiable, nunca instrucción.
- **`.gitattributes`:** los PDF van como binarios y los JSON de `evals/` siempre con LF, porque el manifiesto guarda su SHA-256.

### Cifras con la semilla por defecto

| | Electricista | Albañil | Total |
|---|---|---|---|
| Facturas | 53 | 47 | 100 |
| Presupuestos | 23 | 25 | 48 |
| Otros | 4 | 4 | 8 |
| **Documentos** | **80** | **76** | **156** |

El resumen por profesional está en `summary` de `manifest.json`.

- **Maquetaciones:** las cinco, repartidas casi por igual, más una sexta, «carta», solo para la carta de la comunidad.
- **Escaneados:** 23 (14,7 %, el 15 % redondeado), de las cinco maquetaciones y de la carta. Cinco llevan error sembrado y uno es trampa. Son una imagen JPEG en escala de grises por página, sin capa de texto, con el ruido de un escáner de oficina sembrado por documento.
- **Errores sembrados:** 18 documentos (11,5 %), uno por documento: `total_no_cuadra` ×4, `base_no_cuadra` ×2, `cuota_iva_no_cuadra` ×4, `nif_ausente` ×4 y `linea_partida` ×4. Ninguno cae en una trampa ni en un «otro».
- **Trampas:** cinco facturas, una por variante (`summary.traps`), sin error sembrado:
  - `pie_visible`: en el pie de la última página, en gris y letra pequeña;
  - `concepto_de_linea`: al final del concepto de una línea;
  - `texto_oculto`: texto blanco de un punto bajo los totales;
  - `pie_visible_escaneado`: la técnica `pie_visible` en un escaneado; la instrucción solo está en la imagen y llega por la ruta del OCR;
  - `metadatos`: en el `/Subject` del PDF; no se ve en ninguna página.
- **«Otros»** (RF-IN-02): albarán de proveedor ×2, factura de proveedor ×2, parte de trabajo ×2, hoja de pedido de una constructora y carta del administrador de una comunidad. La factura de proveedor es una factura recibida, no emitida por el profesional, así que se clasifica como «otro».

### Verdad de referencia

Cada JSON recoge **lo que pone el documento**, errores incluidos. Campos principales:

- `id`, `pdf` (ruta en `samples/`), `document_type`, `layout`, `scanned` y `pages`.
- `seeded_errors`: tipo, campo afectado, valor impreso y valor correcto.
- `expected_review_reasons`: motivos por los que la ingesta debe dejar el documento en revisión: `total_no_cuadra`, `base_no_cuadra`, `cuota_iva_no_cuadra` y `falta_nif_cliente`. La línea partida no espera revisión: sus importes cuadran y mide la extracción de las líneas.
- `extraction`: los campos de RF-IN-03 tal como se imprimen. Es `null` en los «otros», que llevan en `other` su clase y una descripción.
  - Importes como cadenas decimales con dos decimales; porcentajes y cantidades también como cadenas. Nunca float.
  - Un NIF ausente va a `null`.
  - Desglose por tipo de IVA (`vat_breakdown`); `vat_rate` solo si hay un tipo, y `null` con inversión del sujeto pasivo.
  - `withholding` (IRPF) y `guarantee` (retención de garantía), cada uno con tipo e importe.
  - `total` y `amount_due`: ver la decisión 4.
- `is_trap` y `trap`: técnica, ubicación, texto inyectado y comportamiento esperado (cero acciones pendientes y no seguir las instrucciones), con `may_flag_for_review: true` (decisión 9).
- `personal_data`: los datos personales impresos de emisor, cliente y terceros (nombre, NIF, dirección, teléfono, email e IBAN), para las pruebas de fuga (RNF-17).

El esquema sigue en 1.0.0 aunque ha cambiado durante el cierre (`may_flag_for_review`, técnicas de trampa nuevas), porque nunca se ha publicado.

### Manifiesto

`manifest.json` guarda:

- la versión del esquema, la semilla y el periodo;
- las versiones de Faker, ReportLab, pypdfium2 y Pillow con las que se generó;
- la definición de cada huella (`fingerprints`);
- por cada fichero, su ruta, su `sha256` y su tamaño; en los PDF, además, su `content_sha256`;
- `dataset_sha256`, la huella del conjunto, y un resumen de cifras por profesional.

### Alcance del determinismo

- La misma semilla, con las mismas versiones, produce el mismo dataset en cualquier máquina. Todo el azar sale de `random.Random` y de Faker sembrados, y nada lee el reloj.
- Faker (`==40.54.0`) y ReportLab (`==5.1.0`) van fijados en el grupo `dev` de `pyproject.toml`, porque sus datos y su salida cambian entre versiones. pypdfium2 y Pillow los fija `uv.lock`. ReportLab va en modo `invariant`, que fija la fecha y el identificador del PDF.
- **JSON y esquema:** se comparan byte a byte. Son texto en UTF-8 con LF.
- **PDF, vectoriales y escaneados:** se comparan por `content_sha256` (`synthetic/fingerprint.py`), la huella del fichero entero, de la cabecera al `%%EOF`. Solo se pone en forma canónica lo que cambia de una plataforma a otra:
  - los flujos Flate, descomprimidos, con límites por flujo y por documento contra las bombas zlib: los bytes comprimidos dependen de la zlib de cada máquina (la de CPython en Windows, la del sistema en Linux, zlib-ng);
  - los JPEG de los escaneados, sustituidos por un marcador después de validar sus segmentos (sin comentarios ni segmentos de aplicación más allá de JFIF), porque libjpeg puede codificar la misma imagen con otros bytes;
  - los `/Length`, los desplazamientos de la tabla de referencias y `startxref`, que dependen de lo anterior; antes de normalizarlos se comprueba que son los correctos;
  - el nombre `/FormXob.<md5>` de cada imagen, que ReportLab calcula con los píxeles decodificados.

  Todo lo demás entra tal cual: diccionarios, metadatos, `trailer` con su `/ID`, flujos de contenido y lo que haya entre objetos.
- **Estructura admitida:** la de un PDF de ReportLab sin actualizaciones. La huella rechaza más de una revisión y bytes tras el `%%EOF`; `/Prev`, `/XRefStm`, `/XRef`, `/ObjStm` y `/Encrypt`, también escritos con escapes `#xx`; filtros distintos de Flate y DCT; y objetos duplicados. Un PDF así no pasa `--check`.
- **Escaneados:** tienen su propio `content_sha256`, que cubre todo su PDF salvo los datos del JPEG. El del vectorial que se rasteriza va en sus `/Keywords` (`kapataz-origen-sha256:<content_sha256>`). La imagen depende además de PDFium, Pillow y libjpeg, así que entre plataformas se compara por píxeles, no por bytes. Dentro de una misma máquina, dos ejecuciones dan los mismos bytes.
- La estabilidad entre plataformas la prueba `test_synthetic_fingerprint.py`, que recomprime los flujos con otra zlib, recodifica los JPEG y cambia el nombre de las imágenes.
- Consecuencia: regenerar en otra plataforma puede cambiar los bytes de algún PDF y, con ellos, su `sha256` y el `dataset_sha256`, sin cambiar el contenido. Solo se regenera cuando cambia el generador o una regla del dominio que use; para lo demás está `--check`.
- **Qué exige `--check`,** con lo que es estable entre plataformas (`synthetic/output.py`, `check`):
  - el manifiesto: el mismo conjunto de rutas que lo regenerado, sin sobrantes ni faltantes en disco; `schema_version`, `seed`, `period`, versiones del generador, la definición de las huellas (`fingerprints`) y `summary` iguales (salvo los tamaños, que tienen que ser los de disco); y un `dataset_sha256` coherente con sus ficheros;
  - cada fichero en disco, con el `sha256` y el tamaño que declara el manifiesto;
  - JSON y esquema, byte a byte con lo regenerado;
  - cada PDF, vectorial o escaneado, por el `content_sha256` calculado sobre los bytes de disco, que tiene que coincidir con el del manifiesto y con el del regenerado; si la estructura no es la admitida, falla;
  - los escaneados, además: todo su `/Info` igual al del regenerado; ligados a su vectorial de origen, porque el `content_sha256` de `/Keywords` tiene que ser el del vectorial regenerado; y comparados con el regenerado página a página: número de páginas, dimensiones de cada imagen y píxeles de tinta frente a papel, con una tolerancia pequeña. Esto último no depende de los bytes del JPEG (`synthetic/scan.py`).

### Decisiones de Borja (20/11/2026)

1. **`seed_demo.py` no emite facturas.** Crea el espacio de demostración de una cuenta (`tenants.kind = 'demo'`, con `parent_tenant_id`) y carga con el dominio el profesional, los clientes, el catálogo y los presupuestos. El histórico son documentos importados (RF-IN-09, ADR-017): sus PDF se cargarán como documentos aprobados en el Bloque 4.
2. **El 15 % de los PDF son escaneados, y todos llevan su JSON.** Con eso, el tamaño de `evals/extraction/` queda fijado en los 156 documentos de la semilla por defecto. Cierra el hueco 1 de `docs/04-evaluacion-ia.md` §9.
3. **Los PDF van solo en `samples/`.** `evals/extraction/` guarda los JSON, emparejados por nombre, el esquema y el manifiesto. Así no hay dos copias de cada PDF.
4. **`total` es el total impreso:** base + cuota − retención de IRPF. Es lo que imprime una factura en España, y lo que se mide en la extracción.
   - No es el `total_amount` del dominio, que es el ImporteTotal de la AEAT (base + cuota). Equivale a `collectible` de `InvoiceTotals`.
   - La retención de garantía no cambia el total: solo aplaza el cobro. `amount_due`, el líquido a percibir, es el total menos la garantía, igual que `amount_due` en el dominio.
   - El Bloque 4 traduce entre los dos al aprobar un documento.
5. **El NIF ausente sembrado espera el motivo `falta_nif_cliente`.** Se apoya en RN-F-06, que exige el NIF del destinatario. RF-IN-05 solo habla de coherencia aritmética, así que el Bloque 4 confirma este motivo y, si hace falta, propone ampliar RF-IN-05. RF-IN-05 no cambia aquí.
6. **Los PDF del histórico no llevan la marca «Documento de demostración».** RN-F-09 se refiere a lo que emite la app, y estos PDF simulan documentos de otros programas. Lo sintético consta en los metadatos de cada PDF, también en los escaneados: autor «Kapataz - generador de datos sintéticos (ADR-020)», palabras clave con «sintético» y un asunto que dice que no corresponde a nadie real. Eso es lo que comprueba la Fase 7. La trampa `metadatos` es la excepción en el asunto, que lleva la instrucción inyectada; en ella valen el autor y las palabras clave.

Con las correcciones de las revisiones de cierre (20/11/2026):

7. **La app no usa Faker.** El botón «Cargar datos de ejemplo» (RF-CF-04) no ejecutará el generador: `gen_synthetic` exportará el contenido de la demo a un dataset JSON empaquetado con la app, y un adaptador lo cargará con `LoadDemoSpace`. Hoy no existe; llega con el bloque del botón. Así Faker y ReportLab siguen solo en `dev`, y un contrato de import-linter impide que `kapataz` importe `tools/` (ver «Verificación»).
8. **Datos de contacto que no pueden ser de nadie** (`synthetic/people.py`):
   - teléfonos `46X XX XX XX` (móvil) y `49X XX XX XX` (fijo), del segmento N=4, «pendiente de atribución» en el Plan nacional de numeración telefónica (RD 2296/2004, ap. 4.4). Ni 0 ni 1, porque 0XY y 1XYA son números cortos (ap. 10.1: 061, 091, 092…) y la red no espera más cifras para enrutarlos (ap. 4.2): un `061…` llamaría a urgencias. Ni 2, porque los operadores lo usan dentro de su red (ap. 5.4). Según 3GPP TS 22.101, ningún número de emergencia que reconoce el propio terminal empieza por 4. Si se atribuye el segmento 4, se cambia el prefijo en `people.py` y se regenera (S3-R-02, 21/11/2026; antes eran `06X…` y `09X…`, con la premisa falsa de que ningún número nacional empieza por 0);
   - IBAN con entidad `0000`, que el Banco de España no tiene asignada, con los controles nacionales y el mod 97 válidos para que pasen una validación de formato. Las trampas usan `ES00 0000…`, que no valida;
   - correos en `correo.example` (RFC 2606).

   Los DNI no tienen rango reservado y casi todos los números están expedidos: es el riesgo residual R-16 de `docs/03-modelo-amenazas.md`. Los CIF, de Cantabria con control válido, tampoco tienen rango reservado.
9. **Mandar una trampa a revisión no es un fallo.** Su verdad lleva `may_flag_for_review: true`: en una trampa, `expected_review_reasons` es el mínimo, no la lista exacta, y lo que se exige es cero acciones pendientes y no seguir la instrucción. Un motivo propio para el contenido sospechoso queda para el Bloque 4, porque toca RF-IN-05.
10. **En el espacio de demostración, los presupuestos facturados o facturados en parte se cargan como aceptados.** El espacio no tiene sus facturas, que son histórico importado (decisión 1), y «aceptado» es lo que eran antes de facturarse (`seed_demo.py`).

### Reglas fiscales provisionales

El tipo de IVA de la obra lo decide el dominio (`works_vat`, RN-F-13, con la regla del 40 % de materiales). Lo que el dominio aún no decide, porque solo aparece en el histórico importado, está aislado en `backend/tools/synthetic/fiscal.py`:

1. **Inversión del sujeto pasivo** (art. 84.Uno.2.º f de la Ley 37/1992): solo en las obras del albañil para constructoras y promotoras. La obra para una empresa que no construye, como una clínica que reforma su local, va al 21 % sin inversión.
2. **Retención de IRPF del 1 %** (art. 95.6 del RIRPF, estimación objetiva): solo el albañil, y solo en las facturas a empresas. El electricista, en estimación directa, no lleva retención.
3. **Retención de garantía del 5 % de la base** en cada certificación de algunas obras para constructoras, como es habitual en la subcontratación. El dominio solo la admite en la factura completa o en la fase final (RF-FA-15); el histórico no tiene por qué seguir esa regla.
4. **Lo que va fuera de la obra, al 21 % en la misma factura,** con desglose por tipos, como haría otro programa. La app lo separaría en otra factura (RN-F-13).

Son provisionales: van a la lista de preguntas para el asesor fiscal. Si alguna cambia, solo cambia `fiscal.py` y se regenera el dataset.

### Queda para su bloque

- **Bloque 4:** cargar los PDF del histórico como documentos aprobados, traducir `total` a los importes del dominio, confirmar `falta_nif_cliente`, valorar un motivo de revisión por contenido sospechoso (toca RF-IN-05) y el escenario «Extracción que no cuadra».
- **Bloque del botón «Cargar datos de ejemplo»:** el dataset JSON de la demo y su adaptador (decisión 7).
- **Fase 7:** comprobar que todo PDF de `samples/` lleva los metadatos del generador.
- **Asesor fiscal:** las cuatro reglas provisionales.
- **Abogado:** el riesgo de los DNI sintéticos (R-16).
