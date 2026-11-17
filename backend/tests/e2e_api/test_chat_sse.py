"""POST /api/chat por SSE con FakeLlm (RF-CO-01, ADR-002, ADR-008)."""

import json
from uuid import UUID

import pytest

from kapataz.domain.accounts.model import TenantId
from kapataz.infrastructure.llm.fake_llm import FakeLlm
from kapataz.infrastructure.payments.fake_subscriptions import FakeSubscriptions
from tests.support import harness, parse_sse

EMAIL = "ana@ejemplo.es"


def _logged_in(h) -> None:
    h.register_and_verify(EMAIL)
    assert h.log_in(EMAIL).status_code == 204


@pytest.mark.req("RF-CO-01")
def test_chat_emite_tokens_en_orden_y_termina_con_done():
    llm = FakeLlm("Hola, esto es una respuesta de prueba.")
    with harness(llm=llm) as h:
        _logged_in(h)
        response = h.post("/api/chat", {"message": "¿Qué le facturé a García?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["token"] * len(llm.chunks) + ["done"]
    texts = [json.loads(data)["text"] for name, data in events if name == "token"]
    assert texts == list(llm.chunks)
    assert "".join(texts) == "Hola, esto es una respuesta de prueba."
    assert json.loads(events[-1][1]) == {}


@pytest.mark.req("RF-CO-01")
def test_chat_entrega_el_mensaje_al_llm():
    llm = FakeLlm()
    with harness(llm=llm) as h:
        _logged_in(h)
        h.post("/api/chat", {"message": "hola"})

    [[turn]] = llm.received
    assert (turn.role, turn.text) == ("user", "hola")


@pytest.mark.req("RNF-08")
def test_fallo_del_llm_a_mitad_llega_como_evento_error():
    llm = FakeLlm("uno dos tres cuatro", fail_after_chunks=2)
    with harness(llm=llm) as h:
        _logged_in(h)
        response = h.post("/api/chat", {"message": "hola"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["token", "token", "error"]
    detail = json.loads(events[-1][1])["detail"]
    assert detail == "El asistente no está disponible ahora. Inténtalo más tarde."


@pytest.mark.req("RF-CO-01")
def test_chat_sin_sesion_responde_401():
    with harness() as h:
        response = h.post("/api/chat", {"message": "hola"})

    assert response.status_code == 401
    assert response.json()["type"] == "/problemas/no-autenticado"


@pytest.mark.req("RF-CO-01")
@pytest.mark.owasp("A01")
def test_chat_sin_csrf_se_rechaza():
    with harness() as h:
        _logged_in(h)
        response = h.client.post("/api/chat", json={"message": "hola"})

    assert response.status_code == 403


@pytest.mark.req("RF-CO-01")
@pytest.mark.parametrize("message", ["", "x" * 4001])
def test_chat_valida_la_longitud_del_mensaje(message):
    with harness() as h:
        _logged_in(h)
        response = h.post("/api/chat", {"message": message})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.req("RF-CO-01")
def test_chat_admite_4000_caracteres():
    with harness() as h:
        _logged_in(h)
        response = h.post("/api/chat", {"message": "x" * 4000})

    assert response.status_code == 200


@pytest.mark.req("RN-12")
def test_chat_sin_suscripcion_activa_responde_403():
    subscriptions = FakeSubscriptions()
    with harness(subscriptions=subscriptions) as h:
        _logged_in(h)
        tenant_id = h.client.get("/api/auth/me").json()["tenant_id"]
        subscriptions.deactivate(TenantId(UUID(tenant_id)))
        response = h.post("/api/chat", {"message": "hola"})

    assert response.status_code == 403
    assert response.json()["type"] == "/problemas/suscripcion-inactiva"
