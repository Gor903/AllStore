from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.storage import storage_healthy
from app.db.session import get_session
from app.deps.settings import settings_dep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    env: str


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    storage: bool


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(settings_dep)]) -> HealthResponse:
    """Liveness: answers 200 without touching dependencies."""
    return HealthResponse(status="ok", env=settings.app_env)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    settings: Annotated[Settings, Depends(settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReadinessResponse:
    """Readiness: verifies the dependencies the app cannot serve traffic without."""
    try:
        await session.execute(text("SELECT 1"))
        database_ok = True
    except SQLAlchemyError:
        database_ok = False
    storage_ok = await storage_healthy(settings)
    healthy = database_ok and storage_ok
    return ReadinessResponse(
        status="ok" if healthy else "degraded",
        database=database_ok,
        storage=storage_ok,
    )
