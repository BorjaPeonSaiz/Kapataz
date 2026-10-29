# ADR-0016: Versionado automático en cada cambio a main y versión visible en el footer

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

Cada cambio que llega a `main` debe generar una versión nueva sin intervención manual, y la aplicación debe mostrar en el footer, en pequeño, qué versión está en producción. Así el equipo y los clientes pueden saber con qué versión están trabajando al reportar un problema.

## Decisión

- **Versionado semántico** (`MAJOR.MINOR.PATCH`) calculado automáticamente con **semantic-release** a partir de los mensajes de commit en formato **Conventional Commits**.
- **Cada merge a `main` publica una versión**, sea cual sea el tipo de cambio:

  | Tipo de commit | Incremento |
  | --- | --- |
  | `feat` | MINOR |
  | `fix`, `perf`, `refactor`, `docs`, `test`, `ci`, `build`, `chore`, `style`, `revert` | PATCH |
  | Cualquier tipo con `!` o `BREAKING CHANGE:` | MAJOR |

- **Pull requests:** se fusionan con *squash merge* y el título del PR se convierte en el mensaje del commit. Un workflow comprueba en cada PR que el título cumple Conventional Commits; si no, el PR no se puede fusionar.
- **Fuente de verdad de la versión:** la etiqueta de Git `vX.Y.Z` y la GitHub Release correspondiente, con las notas generadas a partir de los commits. No se hace commit de vuelta a `main` (no hay fichero `VERSION` ni `CHANGELOG.md` que mantener), para no chocar con la protección de la rama.
- **Versión en las imágenes:** al publicar una versión, el pipeline construye las imágenes de `apps/web` y `apps/agent` etiquetadas con esa versión e inyecta `APP_VERSION` (la versión) y `APP_COMMIT` (SHA corto) como variables de entorno de build. Ninguna aplicación calcula su versión en tiempo de ejecución.
- **Footer:** Laravel lee `APP_VERSION` en `config('app.version')` y la comparte con Inertia como dato común a todas las páginas. El footer de la aplicación de las empresas y del panel de `admin` muestra en texto pequeño y discreto `v1.4.2`. En entornos distintos de producción muestra además el entorno y el commit (`v1.4.2 · staging · a1b2c3d`). En desarrollo local muestra `dev`.
- **API:** el endpoint de salud de Laravel y de FastAPI devuelve también la versión y el commit, para comprobar qué hay desplegado sin abrir la interfaz.
- **Primera versión:** se crea la etiqueta `v0.0.0` sobre el commit inicial para que semantic-release empiece desde ahí; el primer `feat` publicará `v0.1.0`.

## Alternativas consideradas

- **release-please:** abre un PR de versión que hay que fusionar a mano; no cumple «automáticamente en cada cambio».
- **Versión en un fichero actualizado por un commit automático:** obliga a dar al bot permiso para saltarse la protección de `main` y genera commits de ruido.
- **Versión por fecha o por número de build:** no comunica si un cambio es una corrección o una funcionalidad nueva.

## Consecuencias

- Los mensajes de commit y los títulos de PR deben seguir Conventional Commits; las skills y los agentes del proyecto los proponen en ese formato.
- Como todo cambio publica una versión, el número PATCH crecerá rápido; es intencionado.
- Mientras la versión sea `0.x`, un cambio incompatible (`!`) subirá a `1.0.0`. El salto a `1.0.0` debería coincidir con la apertura del registro a clientes.
- El despliegue a producción usa siempre una imagen con versión publicada, así que la versión del footer en producción coincide con una GitHub Release.
