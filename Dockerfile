# Imagen de Kapataz: api y worker (ADR-013, ADR-014).
#
# - Imágenes base fijadas por digest (ADR-022). Para actualizarlas:
#   docker buildx imagetools inspect <imagen>:<etiqueta>
#   y se cambia el digest aquí en un PR.
# - Sin root: el proceso corre como el usuario 10001 y el código es de root,
#   así que la app no puede modificarlo.
# - Se construye siempre desde la raíz del repositorio:
#   docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t kapataz:<commit> .

# ---------------------------------------------------------------- frontend
FROM node:24-trixie-slim@sha256:af02d57b57719b9657a45199a79264a9437940cd55b3c7b3fc99615654f124a0 AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY frontend/ ./
# vite.config.ts deja el build en ../backend/src/kapataz/static.
RUN npm run build

# ---------------------------------------------------------------- uv
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

# ---------------------------------------------------------------- backend
FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS backend

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
# Primero solo las dependencias, para aprovechar la caché de capas.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
# Después el proyecto. Queda instalado en modo editable apuntando a /app/src,
# que se copia tal cual a la imagen final.
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------------------------------------------------------------- final
FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS runtime

ARG GIT_COMMIT=unknown

# Parches de seguridad de Debian publicados después del digest fijado (Trivy
# falla con CVE altos o críticos que ya tienen arreglo). pip sobra: la app
# corre desde /app/.venv, instalado por uv.
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes --quiet pip

RUN groupadd --system --gid 10001 kapataz \
    && useradd --system --uid 10001 --gid kapataz --home-dir /nonexistent \
       --no-create-home --shell /usr/sbin/nologin kapataz \
    && mkdir -p /data/uploads \
    && chown kapataz:kapataz /data/uploads \
    && chmod 0750 /data/uploads

WORKDIR /app
COPY --from=backend /app /app
COPY --from=frontend /build/backend/src/kapataz/static /app/src/kapataz/static

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIT_COMMIT=${GIT_COMMIT} \
    FORWARDED_ALLOW_IPS=127.0.0.1

LABEL org.opencontainers.image.title="kapataz" \
      org.opencontainers.image.revision="${GIT_COMMIT}"

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); sys.exit(0 if r.status == 200 else 1)"]

# FORWARDED_ALLOW_IPS viene del entorno: en producción, la subred de
# kronoqr-app (ADR-014). exec para que uvicorn reciba las señales de parada.
CMD ["sh", "-c", "exec uvicorn kapataz.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
