"""Compose the track use cases with persistence and media adapters."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_depends import get_db
from app.infrastructure.media.cleanup import CleanupService
from app.infrastructure.media.dependencies import get_audio_processor, get_audio_storage
from app.infrastructure.media.repository import FileDeletionRepository
from app.modules.tracks.service import TrackService, UploadLimiter

_upload_limiter = UploadLimiter()


def get_track_service(db: AsyncSession = Depends(get_db)) -> TrackService:
    storage = get_audio_storage()
    return TrackService(db, get_audio_processor(), storage, CleanupService(db, storage),
                        _upload_limiter, FileDeletionRepository(db))
