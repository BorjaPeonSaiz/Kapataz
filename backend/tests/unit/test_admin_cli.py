"""CLI kapataz-admin create-user: cuenta de cortesía ya verificada (RN-13, RF-SA-04)."""

import io

import pytest

from kapataz import admin_cli
from kapataz.bootstrap import Container
from tests.fakes.memory_uow import MemoryUnitOfWorkFactory
from tests.support import STRONG_PASSWORD, harness, make_settings


class _NoEngine:
    async def dispose(self) -> None:
        return None


@pytest.fixture
def memory(monkeypatch):
    factory = MemoryUnitOfWorkFactory()

    def fake_container(settings):
        with harness(settings, uow_factory=factory) as h:
            services = h.client.app.state.services
        return Container(settings=settings, services=services, engine=_NoEngine())

    monkeypatch.setattr(admin_cli, "build_container", fake_container)
    monkeypatch.setattr(admin_cli, "Settings", lambda: make_settings(registration_open=False))
    monkeypatch.setattr(admin_cli, "configure_logging", lambda: None)
    return factory


@pytest.mark.req("RN-13")
@pytest.mark.req("RF-SA-04")
def test_crea_cuenta_verificada_que_puede_iniciar_sesion(memory, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(STRONG_PASSWORD + "\n"))

    code = admin_cli.main(["create-user", "--email", "Cortesia@Ejemplo.es"])

    assert code == 0
    assert "user_id=" in capsys.readouterr().out
    # Con el registro cerrado, la cuenta creada por la CLI entra sin verificar email.
    with harness(make_settings(registration_open=False), uow_factory=memory) as h:
        assert h.log_in("cortesia@ejemplo.es").status_code == 204


@pytest.mark.req("RF-SA-04")
def test_rechaza_email_repetido_y_contrasena_corta(memory, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(STRONG_PASSWORD + "\n"))
    assert admin_cli.main(["create-user", "--email", "ana@ejemplo.es"]) == 0

    monkeypatch.setattr("sys.stdin", io.StringIO(STRONG_PASSWORD + "\n"))
    assert admin_cli.main(["create-user", "--email", "ana@ejemplo.es"]) == 1

    monkeypatch.setattr("sys.stdin", io.StringIO("corta\n"))
    assert admin_cli.main(["create-user", "--email", "luis@ejemplo.es"]) == 1
    assert "No se ha creado la cuenta" in capsys.readouterr().err
