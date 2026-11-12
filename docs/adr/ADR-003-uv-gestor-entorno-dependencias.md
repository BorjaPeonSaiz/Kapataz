# ADR-003 — uv como gestor de entorno y dependencias

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** ninguno funcional. Da soporte a la reproducibilidad de CI (ADR-008) y a la cadena de suministro (ADR-022).

## Contexto

El backend se instala en tres sitios: el portátil de desarrollo, CI en GitHub Actions y la imagen Docker de producción. Las tres instalaciones deben ser idénticas. Si no lo son, una prueba pasa en local y falla en CI, o una dependencia distinta llega a producción sin revisar.

Fuerzas:

- Lockfile con hashes, que exige ADR-022.
- Instalación rápida para que CI sea ágil y la caché sirva.
- Una sola herramienta para la versión de Python, el entorno virtual y la ejecución de comandos (`uv run pytest`, `uv run lint-imports`).

## Opciones consideradas

1. **uv**
   - Ventajas: instalación rápida; lockfile multiplataforma (`uv.lock`) con hashes; gestiona también la versión de Python; usa `pyproject.toml` estándar.
   - Inconvenientes: herramienta más joven que las alternativas; cambia con frecuencia.
2. **Poetry**
   - Ventajas: madura y extendida; lockfile propio.
   - Inconvenientes: más lenta; no gestiona la versión de Python; formato de configuración propio en parte.
3. **pip + pip-tools** (`requirements.txt` compilado con hashes)
   - Ventajas: mínimo número de herramientas; formato universal.
   - Inconvenientes: entorno virtual y versión de Python a mano; varios ficheros de requisitos por grupo; sin comando único para ejecutar.

## Decisión

Opción 1. `backend/pyproject.toml` declara las dependencias y `backend/uv.lock` se versiona en el repositorio.

- Desarrollo, CI e imagen instalan desde el lockfile, sin resolver de nuevo.
- Todos los comandos documentados en `CLAUDE.md` se ejecutan con `uv run`.
- CI usa la caché de uv.
- Python 3.12 queda fijado en el proyecto.

## Consecuencias

- **Positivas**
  - Mismo entorno en los tres sitios.
  - CI más rápida.
  - El lockfile con hashes cubre parte de ADR-022.
- **Negativas y mitigación**
  - Herramienta joven → se fija su versión en CI y en el Dockerfile; como el proyecto usa `pyproject.toml` estándar, cambiar de herramienta solo exige regenerar el lockfile.
  - Un lockfile desactualizado → CI lo detecta (ver Verificación).
- **Qué haría reconsiderarla**
  - Que uv deje de mantenerse o cambie de licencia.
  - Que el lockfile deje de ser reproducible entre plataformas.

## Verificación

- **CI:** `uv sync --locked` falla si `uv.lock` no corresponde a `pyproject.toml`.
- **Dockerfile:** instala con `uv sync --locked`, sin dependencias de desarrollo.
- **CI:** pip-audit revisa las dependencias bloqueadas; un hallazgo alto o crítico bloquea el PR (§7).
- **Revisión de PR:** un cambio de dependencias sin `uv.lock` actualizado no se integra.
