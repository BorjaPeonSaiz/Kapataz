"""Tokens secretos de sesión y de verificación.

El token en claro solo existe en la cookie o en el enlace del email. La base de
datos guarda su SHA-256: quien lea una copia de la tabla no puede abrir sesión.
SHA-256 sin sal basta porque el token tiene 256 bits de entropía; no es una
contraseña elegida por una persona.
"""

import hashlib
import secrets

TOKEN_BYTES = 32


def new_secret_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
