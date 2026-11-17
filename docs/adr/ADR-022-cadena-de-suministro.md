# ADR-022 — Cadena de suministro

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-11, RNF-01, RNF-12 (protección del servicio y de los datos); OWASP A03 y LLM03 (ADR-021)
- **Se cierra en:** Bloque 1. Cerrado el 12/11/2026 (ver «Cierre en el Bloque 1»).

## Contexto

Kapataz depende de muchas piezas de terceros: paquetes de Python y de npm, imágenes base de Docker, acciones de GitHub, el SDK de Anthropic y modelos locales (Whisper, spaCy y el de embeddings). Cualquiera de ellas puede llegar alterada o cambiar sin aviso:

- una dependencia comprometida que roba la clave de la API o los datos de las cuentas;
- una imagen base que cambia bajo la misma etiqueta;
- una acción de CI secuestrada que lee los secretos;
- un modelo local sustituido que degrada la seudonimización (RN-11) sin que se note.

El producto cobra y emite facturas: necesita saber exactamente qué código corre en cada despliegue.

## Opciones consideradas

1. **Rangos de versión sin lockfile.**
   - Ventajas: actualizaciones automáticas, poco mantenimiento.
   - Inconvenientes: cada build puede instalar algo distinto; no hay reproducibilidad ni auditoría.
2. **Lockfile sin hashes y etiquetas móviles** (`python:3.12`, `actions/checkout@v4`).
   - Ventajas: reproducible en la mayoría de los casos; sencillo.
   - Inconvenientes: una etiqueta o un paquete republicado cambian el contenido sin cambiar el nombre.
3. **Todo fijado por contenido: lockfiles con hashes, acciones por SHA, imágenes por digest, modelos por huella y SBOM en cada release.**
   - Ventajas: lo que se instala es exactamente lo revisado; cualquier cambio es un diff visible en un PR.
   - Inconvenientes: las actualizaciones son manuales y más frecuentes; más ruido en los PR.
4. **Réplica privada de paquetes e imágenes.**
   - Ventajas: control total de lo que entra.
   - Inconvenientes: infraestructura que mantener, desproporcionada para un equipo de una persona.

## Decisión

Se elige la opción 3.

- **Python:** `uv.lock` con hashes, usado igual en desarrollo, CI e imágenes (ADR-003). El SDK `anthropic` queda fijado en el lockfile.
- **Frontend:** lockfile de npm e instalación con `npm ci`.
- **CI:** acciones de GitHub fijadas por SHA de commit, no por etiqueta.
- **Imágenes:** imágenes base fijadas por digest.
- **Modelos locales:** Whisper, spaCy y embeddings fijados por versión y huella, incluidos en la imagen o en un volumen, nunca descargados en ejecución y sin telemetría.
- **Auditoría:** `pip-audit`, `npm audit` y Trivy en la etapa de seguridad del CI; gitleaks sobre el historial.
- **SBOM:** CycloneDX en cada release (job `sbom-y-auditoria`).
- **Licencias:** las de dependencias y modelos se revisan para un servicio comercial, con atención a las que afectan al uso por red, como AGPL.
- Las actualizaciones entran por PR y pasan el CI completo como cualquier otro cambio.

## Consecuencias

- **Positivas:**
  - Builds reproducibles y auditables.
  - Un cambio de contenido en cualquier pieza aparece como diff en un PR.
  - El SBOM dice qué contiene cada versión publicada (ADR-032).
- **Negativas y mitigación:**
  - Más trabajo de actualización. Se mitiga agrupando actualizaciones en PR periódicos con el CI como red.
  - Fijar por SHA hace menos legibles los workflows. Se añade la versión como comentario junto al SHA.
  - Los modelos locales aumentan el tamaño de la imagen. Se pueden servir desde un volumen con su huella comprobada.
- **Qué haría reconsiderarla:** un equipo mayor o requisitos de cliente que justifiquen una réplica privada (opción 4).

## Verificación

- Etapa de seguridad del CI: `pip-audit`, `npm audit`, bandit, Semgrep, gitleaks y Trivy sin hallazgos altos ni críticos.
- Job `sbom-y-auditoria` en cada release.
- Check de CI que rechaza un `uses:` de un workflow sin SHA completo y un `FROM` sin digest.
- `test_llm03_huella_modelos_locales`: la huella de cada modelo local coincide con la registrada.
- `uv sync --locked` y `npm ci` en CI: fallan si el lockfile no corresponde a las dependencias declaradas.

## Cierre en el Bloque 1

Implementado:

- **Python:** `backend/uv.lock`, instalado con `uv sync --locked` en CI y en la imagen. FastAPI y uvicorn fijados con `==`.
- **Frontend:** `frontend/package-lock.json`, instalado con `npm ci`.
- **CI:** acciones de terceros fijadas por SHA, con la versión en comentario. Las herramientas de seguridad (Trivy, gitleaks, Semgrep y actionlint) corren en contenedores fijados por digest, no como acciones.
- **Imágenes base** (`Dockerfile` y `docker-compose.yml`) fijadas por digest.
- **Check de plataforma en CI:** rechaza un `uses:` sin SHA completo y un `FROM` o `image:` sin digest.
- **Auditoría:** `pip-audit`, `npm audit --audit-level=high`, bandit, Semgrep, gitleaks sobre el historial y Trivy sobre el repositorio y la imagen.

Estado de la auditoría:

- Python sin vulnerabilidades conocidas. npm sin vulnerabilidades altas: quedan 14 moderadas en herramientas de desarrollo (`minimatch` y `glob`), sin arreglo compatible.
- Trivy limpio con `--ignore-unfixed`. Sin esa opción quedan 49 altas de Debian sin arreglo publicado, que se revisan en cada actualización de la imagen base.

Excepción aceptada (12/11/2026):

- La etapa final del `Dockerfile` hace `apt-get upgrade` sobre la imagen base fijada por digest. Así se corrigen dos CVE altos de zlib que la imagen base aún no traía corregidos. El coste es que dos builds del mismo commit pueden diferir en paquetes de Debian, lo que rompe en parte «lo que se instala es exactamente lo revisado».
- Lo mitiga que Trivy revisa la imagen construida en cada CI.
- Se retira el `upgrade` cuando un digest nuevo de la imagen base traiga esos arreglos. Se revisa en cada actualización del digest.

Queda para su bloque:

- **SBOM** (job `sbom-y-auditoria`): con la primera release, la 1.0.0 (ADR-032).
- **Huella de modelos locales** (`test_llm03_huella_modelos_locales`): cuando entren los modelos (Bloques 4, 5 y 9).
- **Revisión de licencias** de dependencias y modelos: antes de la Parte II.
