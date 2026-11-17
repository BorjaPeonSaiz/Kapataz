"""Cookies de sesión y CSRF (ADR-025)."""

from datetime import datetime

from fastapi import Response

from kapataz.api.csrf import CSRF_COOKIE
from kapataz.domain.accounts.model import SESSION_TTL

SESSION_COOKIE = "kapataz_session"


def set_session_cookie(
    response: Response, token: str, *, expires_at: datetime, now: datetime, secure: bool
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max(0, int((expires_at - now).total_seconds())),
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")


def set_csrf_cookie(response: Response, token: str, *, secure: bool) -> None:
    # Legible por JavaScript a propósito: la SPA la copia en X-CSRF-Token.
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )
