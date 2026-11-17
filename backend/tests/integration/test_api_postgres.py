"""Flujo completo de la API contra PostgreSQL real, con el rol de la app."""

import asyncio
import hashlib
import io
import json
from uuid import UUID

import pytest
from sqlalchemy import text

from kapataz import admin_cli
from kapataz.api.cookies import SESSION_COOKIE
from kapataz.bootstrap import Container, build_services
from kapataz.infrastructure.clock import SystemClock
from kapataz.infrastructure.email.fake_email import FakeEmail
from kapataz.infrastructure.llm.fake_llm import FakeLlm
from kapataz.infrastructure.payments.fake_subscriptions import FakeSubscriptions
from kapataz.infrastructure.persistence.database import SqlDatabaseProbe
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from tests.integration.conftest import APP_ROLE, OWNER_ROLE
from tests.support import STRONG_PASSWORD, fast_hasher, harness, make_settings, parse_sse


def _app_harness(database, **kwargs):
    engine = database.engine(APP_ROLE)
    return harness(
        uow_factory=SqlAlchemyUnitOfWorkFactory(engine),
        database_probe=SqlDatabaseProbe(engine),
        **kwargs,
    )


# Sin req: /api/health es infraestructura; no mide la disponibilidad de RNF-03.
def test_health_con_base_de_datos_real(database):
    with _app_harness(database) as h:
        response = h.client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["checks"]["database"] == "ok"


@pytest.mark.req("RF-AC-01")
@pytest.mark.req("RF-CO-01")
def test_registro_verificacion_login_chat_y_logout(database):
    email = "integracion-flujo@ejemplo.es"
    with _app_harness(database) as h:
        h.register_and_verify(email)
        assert h.log_in(email).status_code == 204
        session_token = h.client.cookies.get(SESSION_COOKIE)

        me = h.client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == email

        chat = h.post("/api/chat", {"message": "hola"})
        assert [name for name, _ in parse_sse(chat.text)][-1] == "done"

        assert h.post("/api/auth/logout").status_code == 204
        h.client.cookies.set(SESSION_COOKIE, session_token)
        assert h.client.get("/api/auth/me").status_code == 401


@pytest.mark.req("RF-AC-01")
@pytest.mark.owasp("A07")
def test_email_repetido_no_crea_otra_cuenta(database):
    email = "integracion-repetido@ejemplo.es"
    with _app_harness(database) as h:
        h.register_and_verify(email)
        response = h.post(
            "/api/auth/register", {"email": email.upper(), "password": STRONG_PASSWORD}
        )
    assert response.status_code == 202

    async def count():
        engine = database.engine(APP_ROLE)
        async with engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT count(*) FROM users WHERE email = :e"), {"e": email}
            )
        await engine.dispose()
        return value

    assert asyncio.run(count()) == 1


@pytest.mark.req("RF-AC-01")
def test_la_base_de_datos_solo_guarda_el_hash_del_token(database):
    email = "integracion-hash@ejemplo.es"
    with _app_harness(database) as h:
        h.register_and_verify(email)
        h.log_in(email)
        token = h.client.cookies.get(SESSION_COOKIE)

    async def stored():
        engine = database.engine(OWNER_ROLE)
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT s.token_hash FROM sessions s JOIN users u ON u.id = s.user_id "
                    "WHERE u.email = :e"
                ),
                {"e": email},
            )
            values = [row[0] for row in rows]
        await engine.dispose()
        return values

    hashes = asyncio.run(stored())
    assert hashes == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in json.dumps(hashes)


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_la_cuenta_creada_solo_es_visible_con_su_cuenta_fijada(database):
    with _app_harness(database) as h:
        h.register_and_verify("integracion-rls@ejemplo.es")
        h.log_in("integracion-rls@ejemplo.es")
        tenant_id = UUID(h.client.get("/api/auth/me").json()["tenant_id"])

    async def visible(fixed):
        engine = database.engine(APP_ROLE)
        async with engine.begin() as conn:
            if fixed is not None:
                await conn.execute(
                    text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(fixed)}
                )
            rows = await conn.execute(text("SELECT id FROM tenants"))
            ids = {row[0] for row in rows}
        await engine.dispose()
        return ids

    assert asyncio.run(visible(None)) == set()
    assert asyncio.run(visible(tenant_id)) == {tenant_id}


@pytest.mark.req("RN-13")
@pytest.mark.req("RF-SA-04")
def test_cli_crea_cuenta_de_cortesia_en_postgresql(database, monkeypatch, capsys):
    settings = make_settings(registration_open=False)

    def container_for_tests(_settings):
        engine = database.engine(APP_ROLE)
        services = build_services(
            settings,
            uow_factory=SqlAlchemyUnitOfWorkFactory(engine),
            database_probe=SqlDatabaseProbe(engine),
            clock=SystemClock(),
            llm=FakeLlm(),
            email=FakeEmail(),
            subscriptions=FakeSubscriptions(),
            hasher=fast_hasher(),
        )
        return Container(settings=settings, services=services, engine=engine)

    monkeypatch.setattr(admin_cli, "build_container", container_for_tests)
    monkeypatch.setattr(admin_cli, "Settings", lambda: settings)
    monkeypatch.setattr(admin_cli, "configure_logging", lambda: None)
    monkeypatch.setattr("sys.stdin", io.StringIO(STRONG_PASSWORD + "\n"))

    assert admin_cli.main(["create-user", "--email", "cortesia-pg@ejemplo.es"]) == 0
    assert "user_id=" in capsys.readouterr().out

    with _app_harness(database, settings=settings) as h:
        assert h.log_in("cortesia-pg@ejemplo.es").status_code == 204
