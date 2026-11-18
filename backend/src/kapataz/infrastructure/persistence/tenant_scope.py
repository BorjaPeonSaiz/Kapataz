"""Cuenta fijada en la unidad de trabajo, compartida por sus repositorios (ADR-024)."""

from uuid import UUID

from kapataz.application.ports.repositories import TenantMismatchError, TenantNotSetError
from kapataz.domain.accounts.model import TenantId


class TenantScope:
    """El código filtra por esta cuenta; RLS lo vuelve a hacer en la base de datos."""

    def __init__(self) -> None:
        self._tenant_id: TenantId | None = None

    def set(self, tenant_id: TenantId) -> None:
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> TenantId:
        if self._tenant_id is None:
            msg = "Repositorio de negocio sin cuenta fijada en la transacción."
            raise TenantNotSetError(msg)
        return self._tenant_id

    def check(self, tenant_id: UUID) -> None:
        """Una entidad de otra cuenta no se escribe: lo impediría también RLS (WITH CHECK)."""
        if tenant_id != self.tenant_id:
            msg = "La entidad no es de la cuenta fijada en la transacción."
            raise TenantMismatchError(msg)
