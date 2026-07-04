"""Liveness/readiness probes.

Deliberately outside `/api/v1` — these are infra-facing (Docker/K8s/Azure
health probes), not part of the versioned public API, and use their own
response shape rather than the standard success/error envelope.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import HealthServiceDep
from app.schemas.health import DependencyCheckSchema, LivenessSchema, ReadinessSchema

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessSchema)
async def liveness() -> LivenessSchema:
    return LivenessSchema(status="ok")


@router.get("/ready")
async def readiness(health_service: HealthServiceDep) -> JSONResponse:
    result = await health_service.check_readiness()
    schema = ReadinessSchema(
        status=result.status,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        checks={
            "database": DependencyCheckSchema(
                status=result.database.status,
                latency_ms=result.database.latency_ms,
                error=result.database.error,
            ),
        },
    )
    return JSONResponse(status_code=200 if result.is_healthy else 503, content=schema.model_dump())
