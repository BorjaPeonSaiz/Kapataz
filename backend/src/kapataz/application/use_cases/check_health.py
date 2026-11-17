"""Estado del servicio: base de datos y LLM por separado (ADR-014, RNF-08)."""

import asyncio
from dataclasses import dataclass

from kapataz.application.ports.llm import LlmPort
from kapataz.application.ports.persistence import DatabaseProbe


@dataclass(frozen=True, slots=True)
class HealthReport:
    version: str
    database_ok: bool
    llm_ok: bool


class CheckHealth:
    def __init__(self, database: DatabaseProbe, llm: LlmPort, version: str) -> None:
        self._database = database
        self._llm = llm
        self._version = version

    async def execute(self) -> HealthReport:
        database_ok, llm_ok = await asyncio.gather(self._database.ping(), self._llm.is_available())
        return HealthReport(version=self._version, database_ok=database_ok, llm_ok=llm_ok)
