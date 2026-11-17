"""Puerto de hash de contraseñas (ADR-025: Argon2id)."""

from typing import Protocol


class PasswordHasher(Protocol):
    async def hash(self, plain: str) -> str: ...

    async def verify(self, password_hash: str, plain: str) -> bool:
        """``True`` si coincide; ``False`` si no o si el hash no es válido. Nunca lanza."""
        ...
