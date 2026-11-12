# ADR-011 — Voz con faster-whisper en nuestro servidor

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RF-VO-01, RF-VO-02, RF-VO-03, RF-VO-04, RF-MO-02, RN-11, RNF-01, RNF-14

## Contexto

El autónomo dicta presupuestos y preguntas desde el móvil, en la obra o al salir de ella (HU-01). Claude no transcribe audio, así que hace falta otra pieza.

Fuerzas:

- La voz y lo que se dice (nombres, direcciones) son datos personales. El audio no se conserva ni se envía a terceros (RF-VO-03), y a Claude nunca llega un audio (RN-11).
- Vocabulario de oficio: diferencial, magnetotérmico, rozas, alicatado, solera (RF-VO-04).
- Un audio de 30 s se transcribe en menos de 15 s en el servidor de referencia (RNF-14).
- El servidor es un VPS que comparte CPU entre la API, el OCR y los embeddings (ADR-014).
- Debe funcionar en Chrome, Edge y Safari, en Android y en iOS (RF-MO-02).

## Opciones consideradas

1. **faster-whisper en nuestro servidor**, en el worker y con concurrencia limitada.
   - Ventajas: el audio no sale del servidor; prompt inicial con vocabulario de oficio; mismo resultado en todos los navegadores.
   - Inconvenientes: consume CPU; el modelo aumenta el tamaño de la imagen o necesita un volumen.
2. **API de transcripción de un tercero**
   - Ventajas: rápida y sin CPU propia.
   - Inconvenientes: el audio sale hacia otro proveedor, en contra de RF-VO-03; un subencargado más.
3. **Reconocimiento de voz del navegador (Web Speech API)**
   - Ventajas: sin coste de servidor.
   - Inconvenientes: soporte desigual entre navegadores; en algunos el audio lo procesan servidores del fabricante, fuera de nuestro control; sin prompt de vocabulario.

## Decisión

Opción 1.

- `TranscriptionPort` → `FasterWhisper`, ejecutado en el worker (ADR-026) con concurrencia limitada para no agotar la CPU.
- El cliente graba con MediaRecorder en los formatos de Chrome, Edge y Safari y envía el audio al endpoint de transcripción.
- La transcripción se muestra editable antes de enviarse al chat (RF-VO-02).
- El audio se borra al terminar la transcripción, también si falla (RF-VO-03).
- El prompt inicial con vocabulario de oficio es configurable (RF-VO-04).
- El modelo va incluido en la imagen o en un volumen; nunca se descarga en ejecución.
- El tamaño del modelo se elige en el Bloque 9 con WER y RNF-14 medidos.

## Consecuencias

- **Positivas**
  - El audio no sale del servidor ni se conserva.
  - El texto transcrito sigue el mismo camino que el escrito: seudonimización antes de Claude.
- **Negativas y mitigación**
  - Competencia por la CPU → concurrencia limitada en el worker, en una cola donde una cuenta no acapara al resto (ADR-026).
  - Latencia frente a RNF-14 → se mide en el Bloque 9; si no se cumple, modelo menor o más CPU.
  - Errores de transcripción → texto editable antes de enviar y WER medido sobre 30–50 grabaciones reales con frases de oficio.
- **Qué haría reconsiderarla**
  - No cumplir RNF-14 en el servidor de referencia con ningún tamaño de modelo aceptable en WER.
  - Que Claude acepte audio con garantías equivalentes; aun así, RN-11 lo impide mientras siga vigente.

## Verificación

- **import-linter:** `faster_whisper` solo se importa desde `kapataz.infrastructure.speech`.
- `tests/integration/speech/test_borrado_audio.py`: tras transcribir, y tras forzar un fallo, el fichero de audio no existe. `@pytest.mark.req("RF-VO-03")`.
- `tests/integration/speech/test_transcripcion_editable.py`: el endpoint devuelve el texto y no envía nada al chat hasta que el usuario lo manda. `@pytest.mark.req("RF-VO-02")`.
- `tests/integration/speech/test_prompt_inicial.py`: el prompt de vocabulario configurado llega al adaptador. `@pytest.mark.req("RF-VO-04")`.
- **Arranque sin red:** el worker arranca y transcribe sin acceso a internet, lo que prueba que el modelo no se descarga.
- **Medición** en el Bloque 9: RNF-14 en el servidor de referencia y WER anotado; escenario de presupuesto por voz de extremo a extremo en Android y en iOS.
