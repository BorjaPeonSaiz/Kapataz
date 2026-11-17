"""Hash de contraseñas con Argon2id (ADR-025), con argon2-cffi."""

import asyncio

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    """Parámetros por defecto de argon2-cffi (perfil RFC 9106 de poca memoria).

    El cálculo es deliberadamente costoso, así que corre en un hilo para no
    bloquear el bucle de eventos mientras se atienden otras peticiones.
    """

    def __init__(self, *, time_cost: int = 3, memory_cost_kib: int = 65536) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=4, type=Type.ID
        )

    async def hash(self, plain: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, plain)

    async def verify(self, password_hash: str, plain: str) -> bool:
        return await asyncio.to_thread(self._verify, password_hash, plain)

    def _verify(self, password_hash: str, plain: str) -> bool:
        try:
            return self._hasher.verify(password_hash, plain)
        except (VerificationError, InvalidHashError):
            return False
