"""uvicorn acepta X-Forwarded-* solo de la subred de kronoqr-app (ADR-014).

Comprueba con el middleware real de uvicorn que ``--forwarded-allow-ips``
admite un rango CIDR, como exige el despliegue detrás del nginx de KronoQR.
"""

import asyncio

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# Sin req: comprueba el middleware de uvicorn con la subred de ADR-014; no comprueba HTTPS
# ni HSTS (RNF-12).

TRUSTED = "172.18.0.0/16"


def _seen_by_app(client_host: str) -> tuple[tuple[str, int], str]:
    seen: dict[str, object] = {}

    async def app(scope, receive, send):
        seen["client"] = scope["client"]
        seen["scheme"] = scope["scheme"]

    middleware = ProxyHeadersMiddleware(app, trusted_hosts=TRUSTED)
    scope = {
        "type": "http",
        "scheme": "http",
        "client": (client_host, 40000),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.9"),
            (b"x-forwarded-proto", b"https"),
        ],
    }
    asyncio.run(middleware(scope, None, None))
    return seen["client"], seen["scheme"]


@pytest.mark.parametrize("proxy_ip", ["172.18.0.7", "172.18.255.254"])
def test_proxy_de_la_subred_es_de_confianza(proxy_ip):
    client, scheme = _seen_by_app(proxy_ip)
    assert client[0] == "203.0.113.9"
    assert scheme == "https"


@pytest.mark.owasp("A02")
@pytest.mark.parametrize("other_ip", ["172.19.0.7", "10.0.0.5", "203.0.113.50"])
def test_fuera_de_la_subred_se_ignoran_las_cabeceras(other_ip):
    client, scheme = _seen_by_app(other_ip)
    assert client[0] == other_ip
    assert scheme == "http"
