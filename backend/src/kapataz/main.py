"""Punto de entrada ASGI.

``uvicorn kapataz.main:app --host 0.0.0.0 --port 8000 --proxy-headers
--forwarded-allow-ips 172.18.0.0/16`` (ADR-014).
"""

from kapataz.bootstrap import build_app

app = build_app()
