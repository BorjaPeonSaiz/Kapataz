"""Tokens CSRF firmados para el patrón de doble envío (ADR-025)."""

import base64
import hashlib
import hmac
import secrets

CSRF_COOKIE = "kapataz_csrf"
CSRF_HEADER = "X-CSRF-Token"
_NONCE_BYTES = 32


class CsrfTokens:
    def __init__(self, secret_key: str) -> None:
        self._key = hashlib.sha256(b"kapataz-csrf:" + secret_key.encode("utf-8")).digest()

    def issue(self) -> str:
        nonce = secrets.token_urlsafe(_NONCE_BYTES)
        return f"{nonce}.{self._sign(nonce)}"

    def is_valid(self, token: str | None) -> bool:
        if not token or token.count(".") != 1:
            return False
        nonce, signature = token.split(".")
        # Se compara en bytes: compare_digest rechaza str con caracteres no ASCII.
        return bool(nonce) and hmac.compare_digest(
            signature.encode("utf-8"), self._sign(nonce).encode("utf-8")
        )

    def matches(self, cookie: str | None, header: str | None) -> bool:
        if not cookie or not header:
            return False
        same = hmac.compare_digest(cookie.encode("utf-8"), header.encode("utf-8"))
        return same and self.is_valid(cookie)

    def _sign(self, nonce: str) -> str:
        digest = hmac.new(self._key, nonce.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
