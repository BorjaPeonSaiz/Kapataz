"""GET /api/health: base de datos y LLM por separado (ADR-014, RNF-08)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from kapataz.api.dependencies import Services
from kapataz.api.schemas.health import HealthChecks, HealthResponse

router = APIRouter(tags=["salud"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio",
    responses={503: {"model": HealthResponse, "description": "La base de datos no responde"}},
)
async def health(services: Services) -> JSONResponse:
    report = await services.check_health.execute()
    body = HealthResponse(
        # Sin LLM la app sigue sirviendo todo lo demás: 200 «degraded» (RNF-08).
        # Sin base de datos no sirve nada: 503.
        status="ok" if report.database_ok and report.llm_ok else "degraded",
        version=report.version,
        checks=HealthChecks(
            database="ok" if report.database_ok else "error",
            llm="ok" if report.llm_ok else "error",
        ),
    )
    return JSONResponse(body.model_dump(), status_code=200 if report.database_ok else 503)
