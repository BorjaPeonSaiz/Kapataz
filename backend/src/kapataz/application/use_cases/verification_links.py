"""Enlaces que se envían por email y abren una pantalla de la SPA."""

from dataclasses import dataclass
from urllib.parse import urlencode

# Ruta de la SPA que recoge el token y llama a POST /api/auth/verify-email.
EMAIL_VERIFICATION_PATH = "/verificar-email"


@dataclass(frozen=True, slots=True)
class VerificationLinkBuilder:
    public_base_url: str

    def email_verification(self, token: str) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}{EMAIL_VERIFICATION_PATH}?{urlencode({'token': token})}"
