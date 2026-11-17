"""Cuentas: CSRF, registro, verificación, inicio y cierre de sesión (RF-AC-01, ADR-025)."""

from fastapi import APIRouter, Request, Response, status

from kapataz.api.cookies import (
    SESSION_COOKIE,
    clear_session_cookie,
    set_csrf_cookie,
    set_session_cookie,
)
from kapataz.api.csrf import CSRF_COOKIE
from kapataz.api.dependencies import Csrf, CurrentSettings, CurrentUser, Services
from kapataz.api.errors import problem_openapi_responses
from kapataz.api.schemas.auth import LoginRequest, MeResponse, RegisterRequest, VerifyEmailRequest

router = APIRouter(prefix="/auth", tags=["cuentas"])


@router.get(
    "/csrf",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Entrega la cookie kapataz_csrf",
    description=(
        "Fija la cookie `kapataz_csrf`, legible por JavaScript. Toda petición con método "
        "no seguro bajo /api debe enviar su valor en la cabecera `X-CSRF-Token`."
    ),
)
async def csrf(request: Request, tokens: Csrf, settings: CurrentSettings) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    current = request.cookies.get(CSRF_COOKIE)
    # Se reutiliza el token vigente para que varias pestañas no se pisen.
    token = current if tokens.is_valid(current) and current is not None else tokens.issue()
    set_csrf_cookie(response, token, secure=settings.cookie_secure)
    return response


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    summary="Registro con verificación de email",
    description=(
        "Responde 202 tanto si el email es nuevo como si ya existe, para no revelar "
        "qué emails tienen cuenta. Con el registro cerrado (RN-13) solo admite los "
        "emails habilitados."
    ),
    responses=problem_openapi_responses(403, 422),
)
async def register(body: RegisterRequest, services: Services) -> Response:
    await services.register_account.execute(body.email, body.password)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post(
    "/verify-email",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Verifica el email con el token del enlace",
    responses=problem_openapi_responses(400, 403, 422),
)
async def verify_email(body: VerifyEmailRequest, services: Services) -> Response:
    await services.verify_email.execute(body.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/login",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Inicia sesión y fija la cookie kapataz_session",
    responses=problem_openapi_responses(401, 403, 422),
)
async def login(
    body: LoginRequest, request: Request, services: Services, settings: CurrentSettings
) -> Response:
    issued = await services.log_in.execute(
        body.email, body.password, previous_session_token=request.cookies.get(SESSION_COOKIE)
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_session_cookie(
        response,
        issued.token,
        expires_at=issued.expires_at,
        now=services.clock.now(),
        secure=settings.cookie_secure,
    )
    return response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cierra la sesión y la revoca en el servidor",
    responses=problem_openapi_responses(403),
)
async def logout(request: Request, services: Services, settings: CurrentSettings) -> Response:
    await services.log_out.execute(request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, secure=settings.cookie_secure)
    return response


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Usuario de la sesión",
    responses=problem_openapi_responses(401),
)
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(user_id=user.user_id, email=user.email, tenant_id=user.tenant_id)
