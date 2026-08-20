from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    version: str
    checks: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health(settings=Depends(get_settings)) -> HealthResponse:
    checks = {
        "database_configured": settings.database_configured,
        "qdrant_configured": settings.qdrant_configured,
        "groq_configured": settings.groq_configured,  # <-- Added Groq check
        "cors_origins_configured": len(settings.cors_origin_list) > 0,
        "debug_enabled": settings.debug,
    }

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.environment,
        version=settings.app_version,
        checks=checks,
    )