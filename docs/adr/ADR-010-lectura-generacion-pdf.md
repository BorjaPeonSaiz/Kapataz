# ADR-010 — Lectura y generación de PDF

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-IN-01, RF-IN-03, RF-IN-04, RF-IN-05, RF-IN-06, RF-PR-06, RF-FA-07, RN-11, RN-F-09, RNF-01, RNF-05, RNF-06

## Contexto

**Lectura.** El usuario importa sus facturas y presupuestos antiguos en PDF (RF-IN-01). Algunos tienen texto y tablas; otros son escaneados. Claude extrae los datos estructurados (RF-IN-03), pero a Claude nunca llega un PDF, una imagen ni un audio: solo texto seudonimizado (RN-11). Un PDF puede ser malicioso, estar cifrado o ser enorme. La ingesta de una página debe tardar menos de 30 s (RNF-05).

**Generación.** La app genera el PDF de presupuestos (RF-PR-06) y facturas (RF-FA-07) con los datos obligatorios, el logotipo opcional, la marca de demostración solo en ese espacio (RN-F-09) y, desde el Bloque 12, el QR de Verifactu (RF-VF-02). La imagen Docker debe ser sencilla de construir y de auditar.

## Opciones consideradas

**Lectura**

1. **pdfplumber para texto y tablas, Tesseract para escaneados, en nuestro servidor**
   - Ventajas: el PDF no sale del servidor; el texto pasa por la seudonimización antes de llegar a Claude; `OcrPort` sirve después para fotos de tiques (§1.4).
   - Inconvenientes: se pierde parte de la maquetación; el OCR consume CPU.
2. **Enviar el PDF a Claude**
   - Ventajas: el modelo ve la maquetación completa.
   - Inconvenientes: incumple RN-11; nombres, NIF y direcciones saldrían sin seudonimizar.
3. **OCR en un servicio en la nube**
   - Ventajas: más rápido y sin CPU propia.
   - Inconvenientes: otro proveedor que trata datos personales (RNF-01).

**Generación**

4. **ReportLab**
   - Ventajas: sin dependencias nativas; control fino de la página.
   - Inconvenientes: la maquetación se escribe en código, más largo que una plantilla HTML.
5. **HTML y CSS convertidos a PDF**
   - Ventajas: plantillas fáciles de diseñar.
   - Inconvenientes: el conversor necesita librerías nativas en la imagen.

## Decisión

Opciones 1 y 4.

- `PdfTextPort` → `PdfPlumberReader`; `OcrPort` → `TesseractOcr`, con el idioma español.
- Se rechazan con un motivo claro los PDF cifrados o enormes (Bloque 4).
- El texto leído pasa por `PseudonymizerPort`; `LlmPort` solo acepta `SanitizedPrompt`, que es texto.
- La lectura y el OCR corren en el worker (ADR-026).
- `PdfRenderPort` → `ReportLabRenderer`, con el sistema visual de `ui-ux`.

## Consecuencias

- **Positivas**
  - Ningún documento sale del servidor hacia Claude.
  - Imagen sin dependencias nativas para generar PDF.
- **Negativas y mitigación**
  - Pérdida de maquetación al leer → confianza por campo (RF-IN-04), validación aritmética por código (RF-IN-05) y revisión manual antes de contar (RF-IN-06). La precisión se mide con RNF-06.
  - CPU del OCR → cola en el worker con concurrencia limitada; RNF-05 medido en el Bloque 4.
  - Maquetación en código → un único renderizador para presupuestos y facturas.
- **Qué haría reconsiderarla**
  - No alcanzar RNF-06 por la calidad del texto extraído.
  - Que ReportLab no permita el diseño o el QR que exige el Bloque 12.

## Verificación

- **import-linter:** pdfplumber y ReportLab solo se importan desde `kapataz.infrastructure.pdf`.
- **mypy `--strict`:** `LlmPort` no acepta `bytes`, solo `SanitizedPrompt`.
- `tests/security/test_ingesta_sin_pdf_hacia_llm.py`: al importar un PDF de `samples/`, lo que captura `FakeLlm` es texto seudonimizado y no contiene el fichero. `@pytest.mark.req("RN-11")`.
- `tests/integration/documents/test_pdf_rechazado.py`: un PDF cifrado se rechaza con motivo visible. `@pytest.mark.req("RF-IN-01")`.
- `tests/integration/pdf/test_pdf_factura.py`: se genera el PDF de una factura y, al leerlo con pdfplumber, contiene todos los datos obligatorios. `@pytest.mark.req("RF-FA-07")`.
- `tests/integration/pdf/test_marca_demo.py`: la marca «Documento de demostración» solo aparece en el espacio de demostración. `@pytest.mark.req("RN-F-09")`.
- **Medición** de RNF-05 y RNF-06 en el Bloque 4, con informe en `docs/04-evaluacion-ia.md`.
