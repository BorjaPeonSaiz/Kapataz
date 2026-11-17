"""Raíz de composición: decide qué adaptador va detrás de cada puerto (ADR-001).

Queda fuera del contrato de capas: es el único sitio que conoce a la vez la
configuración, los adaptadores concretos y los casos de uso.
"""

from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from kapataz.api.app import create_app
from kapataz.application.ports.email import EmailPort
from kapataz.application.ports.llm import LlmPort
from kapataz.application.ports.persistence import DatabaseProbe, UnitOfWorkFactory
from kapataz.application.ports.security import PasswordHasher
from kapataz.application.ports.subscriptions import SubscriptionPort
from kapataz.application.services import AppServices
from kapataz.application.use_cases.authenticate_session import AuthenticateSession
from kapataz.application.use_cases.check_health import CheckHealth
from kapataz.application.use_cases.create_courtesy_account import CreateCourtesyAccount
from kapataz.application.use_cases.log_in import LogIn
from kapataz.application.use_cases.log_out import LogOut
from kapataz.application.use_cases.register_account import RegisterAccount
from kapataz.application.use_cases.stream_chat_reply import StreamChatReply
from kapataz.application.use_cases.verification_links import VerificationLinkBuilder
from kapataz.application.use_cases.verify_email import VerifyEmail
from kapataz.domain.clock import Clock
from kapataz.infrastructure.clock import SystemClock
from kapataz.infrastructure.email.fake_email import FakeEmail
from kapataz.infrastructure.email.smtp_email import SmtpEmail
from kapataz.infrastructure.llm.fake_llm import FakeLlm
from kapataz.infrastructure.logging.setup import configure_logging
from kapataz.infrastructure.payments.fake_subscriptions import FakeSubscriptions
from kapataz.infrastructure.persistence.database import SqlDatabaseProbe, create_engine
from kapataz.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWorkFactory
from kapataz.infrastructure.security.argon2_hasher import Argon2PasswordHasher
from kapataz.infrastructure.settings import Settings

# Pausa entre trozos del FakeLlm fuera de las pruebas, para que el streaming se vea.
FAKE_LLM_CHUNK_DELAY_SECONDS = 0.04


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    services: AppServices
    engine: AsyncEngine

    async def aclose(self) -> None:
        await self.engine.dispose()


def build_services(
    settings: Settings,
    *,
    uow_factory: UnitOfWorkFactory,
    database_probe: DatabaseProbe,
    clock: Clock,
    llm: LlmPort,
    email: EmailPort,
    subscriptions: SubscriptionPort,
    hasher: PasswordHasher,
) -> AppServices:
    return AppServices(
        clock=clock,
        register_account=RegisterAccount(
            uow_factory,
            hasher,
            email,
            clock,
            settings.registration_policy,
            VerificationLinkBuilder(settings.public_base_url),
        ),
        verify_email=VerifyEmail(uow_factory, clock),
        log_in=LogIn(uow_factory, hasher, clock),
        log_out=LogOut(uow_factory, clock),
        authenticate_session=AuthenticateSession(uow_factory, clock),
        stream_chat_reply=StreamChatReply(llm, subscriptions),
        check_health=CheckHealth(database_probe, llm, settings.git_commit),
        create_courtesy_account=CreateCourtesyAccount(uow_factory, hasher, clock),
    )


def build_llm(settings: Settings) -> LlmPort:
    match settings.llm_backend:
        case "fake":
            return FakeLlm(delay_seconds=FAKE_LLM_CHUNK_DELAY_SECONDS)


def build_email(settings: Settings) -> EmailPort:
    match settings.email_backend:
        case "fake":
            return FakeEmail()
        case "smtp":
            if settings.smtp_host is None or settings.smtp_from is None:
                msg = "EMAIL_BACKEND=smtp necesita SMTP_HOST y SMTP_FROM."
                raise ValueError(msg)
            return SmtpEmail(
                host=settings.smtp_host,
                port=settings.smtp_port,
                sender=settings.smtp_from,
                user=settings.smtp_user,
                password=(
                    settings.smtp_password.get_secret_value() if settings.smtp_password else None
                ),
            )


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url)
    services = build_services(
        settings,
        uow_factory=SqlAlchemyUnitOfWorkFactory(engine),
        database_probe=SqlDatabaseProbe(engine),
        clock=SystemClock(),
        llm=build_llm(settings),
        email=build_email(settings),
        # Hasta el Bloque 10 (Stripe) toda cuenta tiene la suscripción activa.
        subscriptions=FakeSubscriptions(),
        hasher=Argon2PasswordHasher(),
    )
    return Container(settings=settings, services=services, engine=engine)


def build_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved = settings if settings is not None else Settings()
    container = build_container(resolved)
    return create_app(resolved, container.services, on_shutdown=container.aclose)
