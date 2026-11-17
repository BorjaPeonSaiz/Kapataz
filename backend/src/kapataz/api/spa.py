"""Sirve el build de Vue desde ``kapataz/static`` en el mismo origen que la API (ADR-013)."""

import mimetypes
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Vite pone en assets/ los ficheros con hash en el nombre: nunca cambian.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# index.html, el manifiesto y el service worker se revalidan siempre, para que
# la PWA detecte la versión nueva (RF-MO-04).
NO_CACHE = "no-cache"

# En Windows el registro puede asignar text/plain a .js; con nosniff el
# navegador no lo ejecutaría. Se fijan los tipos que usa el build.
for _extension, _media_type in (
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".css", "text/css"),
    (".svg", "image/svg+xml"),
    (".webmanifest", "application/manifest+json"),
    (".woff2", "font/woff2"),
    (".json", "application/json"),
):
    mimetypes.add_type(_media_type, _extension)


def install_spa(app: FastAPI, static_dir: Path, *, reserved_paths: frozenset[str]) -> None:
    """Ruta comodín final. Si no hay build, todo responde 404 sin romper la API."""
    root = static_dir.resolve()

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        path = PurePosixPath(full_path)
        if full_path in reserved_paths or (path.parts and path.parts[0] == "api"):
            raise HTTPException(status_code=404)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)

        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                is_hashed = path.parts[0] == "assets"
                return FileResponse(
                    candidate,
                    headers={"Cache-Control": IMMUTABLE_CACHE if is_hashed else NO_CACHE},
                )
            if path.suffix:
                # Un fichero que no existe no es una ruta de la SPA.
                raise HTTPException(status_code=404)

        return FileResponse(index, headers={"Cache-Control": NO_CACHE})
