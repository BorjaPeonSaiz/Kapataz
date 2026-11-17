"""GET /api/health: base de datos y LLM por separado."""

import pytest

from kapataz.infrastructure.llm.fake_llm import FakeLlm
from tests.support import StubDatabaseProbe, harness

# Sin req en las pruebas de /api/health salvo RNF-08: el endpoint es infraestructura de
# despliegue y no mide la disponibilidad mensual de RNF-03.


def test_health_ok_con_version():
    with harness() as h:
        response = h.client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "abc1234",
        "checks": {"database": "ok", "llm": "ok"},
    }


@pytest.mark.req("RNF-08")
def test_health_sin_llm_sigue_en_200_degradado():
    with harness(llm=FakeLlm(available=False)) as h:
        response = h.client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"] == {"database": "ok", "llm": "error"}


def test_health_sin_base_de_datos_responde_503():
    with harness(database_probe=StubDatabaseProbe(ok=False)) as h:
        response = h.client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["database"] == "error"


def test_health_no_exige_csrf_ni_sesion():
    with harness() as h:
        assert h.client.get("/api/health").status_code == 200
        assert "set-cookie" not in h.client.get("/api/health").headers
