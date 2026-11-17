"""Dependencias de FastAPI: casos de uso, configuración y usuario autenticado."""

from typing import Annotated

import structlog
from fastapi import Depends, Request

from kapataz.api.cookies import SESSION_COOKIE
from kapataz.api.csrf import CsrfTokens
from kapataz.application.services import AppServices
from kapataz.domain.accounts.model import AuthenticatedUser
from kapataz.infrastructure.settings import Settings


def get_services(request: Request) -> AppServices:
    services: AppServices = request.app.state.services
    return services


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_csrf_tokens(request: Request) -> CsrfTokens:
    tokens: CsrfTokens = request.app.state.csrf_tokens
    return tokens


Services = Annotated[AppServices, Depends(get_services)]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
Csrf = Annotated[CsrfTokens, Depends(get_csrf_tokens)]


async def get_current_user(request: Request, services: Services) -> AuthenticatedUser:
    user = await services.authenticate_session.execute(request.cookies.get(SESSION_COOKIE))
    # Desde aquí, cada línea de log de la petición lleva la cuenta (ADR-015).
    structlog.contextvars.bind_contextvars(tenant_id=str(user.tenant_id))
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
