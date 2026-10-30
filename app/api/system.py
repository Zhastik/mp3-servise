"""Operational endpoints separated from business use cases."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.database import check_connection
from app.infrastructure.media.dependencies import get_audio_processor
from app.modules.tracks.ports import AudioProcessor
from app.modules.tracks.schemas import UploadStatus

router = APIRouter(tags=["Health"])


class HealthStatus(BaseModel):
    status: str = "ok"
    service: str = "volna"
    version: str = "1.0.0"


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    await check_connection()
    return HealthStatus()


@router.get("/api/status", response_model=UploadStatus)
async def upload_status(processor: AudioProcessor = Depends(get_audio_processor)) -> dict:
    return await processor.status()
