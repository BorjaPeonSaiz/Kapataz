"""Utilidades compartidas: configuración de prueba y app con adaptadores falsos."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient

from kapataz.api.app import create_app
from kapataz.api.csrf import CSRF_COOKIE, CSRF_HEADER
from kapataz.application.ports.email import EmailPort
from kapataz.application.ports.persistence import DatabaseProbe, UnitOfWorkFactory
from kapataz.bootstrap import build_services
from kapataz.infrastructure.clock import FrozenClock
from kapataz.infrastructure.email.fake_email import FakeEmail
from kapataz.infrastructure.llm.fake_llm import FakeLlm
from kapataz.infrastructure.payments.fake_subscriptions import FakeSubscriptions
from kapataz.infrastructure.security.argon2_hasher import Argon2PasswordHasher
from kapataz.infrastructure.settings import Settings
from tests.fakes.memory_uow import MemoryUnitOfWorkFactory

TEST_SECRET_KEY = "clave-de-pruebas-que-no-es-secreta-0123456789"  # gitleaks:allow (solo pruebas)
STRONG_PASSWORD = "caballo-grapa-bateria-correcta"
NO_STATIC_DIR = Path(__file__).parent / "_sin_build_de_vue"
START = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "local",
        "database_url": "postgresql://kapataz_app:x@localhost:5432/kapataz",
        "secret_key": TEST_SECRET_KEY,
        "public_base_url": "https://kapataz.test",
        "llm_backend": "fake",
        "registration_open": True,
        "registration_allowlist": "",
        "email_backend": "fake",
        "cookie_secure": True,
        "git_commit": "abc1234",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def fast_hasher() -> Argon2PasswordHasher:
    """Argon2id con coste mínimo: mismo algoritmo, pruebas rápidas."""
    return Argon2PasswordHasher(time_cost=1, memory_cost_kib=64)


class StubDatabaseProbe:
    def __init__(self, *, ok: bool = True, error: Exception | None = None) -> None:
        self.ok = ok
        self.error = error

    async def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.ok


@dataclass
class Harness:
    client: TestClient
    settings: Settings
    email: FakeEmail
    llm: FakeLlm
    clock: FrozenClock
    uow_factory: UnitOfWorkFactory

    def csrf_token(self) -> str:
        token = self.client.cookies.get(CSRF_COOKIE)
        if token is None:
            response = self.client.get("/api/auth/csrf")
            assert response.status_code == 204
            token = self.client.cookies.get(CSRF_COOKIE)
        assert token is not None
        return token

    def post(self, path: str, json: dict[str, Any] | None = None) -> httpx.Response:
        return self.client.post(path, json=json, headers={CSRF_HEADER: self.csrf_token()})

    def last_verification_token(self) -> str:
        url = self.email.sent[-1].verification_url
        return parse_qs(urlsplit(url).query)["token"][0]

    def register_and_verify(self, email: str, password: str = STRONG_PASSWORD) -> None:
        response = self.post("/api/auth/register", {"email": email, "password": password})
        assert response.status_code == 202, response.text
        response = self.post("/api/auth/verify-email", {"token": self.last_verification_token()})
        assert response.status_code == 204, response.text

    def log_in(self, email: str, password: str = STRONG_PASSWORD) -> httpx.Response:
        return self.post("/api/auth/login", {"email": email, "password": password})


@contextmanager
def harness(
    settings: Settings | None = None,
    *,
    llm: FakeLlm | None = None,
    subscriptions: FakeSubscriptions | None = None,
    database_probe: DatabaseProbe | None = None,
    uow_factory: UnitOfWorkFactory | None = None,
    email_port: EmailPort | None = None,
    static_dir: Path = NO_STATIC_DIR,
    base_url: str = "https://testserver",
) -> Iterator[Harness]:
    resolved = settings or make_settings()
    clock = FrozenClock(START)
    email = FakeEmail()
    fake_llm = llm or FakeLlm()
    factory = uow_factory or MemoryUnitOfWorkFactory()
    services = build_services(
        resolved,
        uow_factory=factory,
        database_probe=database_probe or StubDatabaseProbe(),
        clock=clock,
        llm=fake_llm,
        email=email_port or email,
        subscriptions=subscriptions or FakeSubscriptions(),
        hasher=fast_hasher(),
    )
    app = create_app(resolved, services, static_dir=static_dir)
    with TestClient(app, base_url=base_url) as client:
        yield Harness(
            client=client,
            settings=resolved,
            email=email,
            llm=fake_llm,
            clock=clock,
            uow_factory=factory,
        )


def parse_sse(body: str) -> list[tuple[str, str]]:
    """Convierte un cuerpo SSE en una lista de (evento, data)."""
    events: list[tuple[str, str]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], fields["data"]))
    return events


def set_cookie_headers(response: httpx.Response, name: str) -> list[str]:
    return [
        value for value in response.headers.get_list("set-cookie") if value.startswith(f"{name}=")
    ]
