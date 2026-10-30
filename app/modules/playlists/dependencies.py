"""Request-scoped playlist service construction."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_depends import get_db
from app.modules.playlists.service import PlaylistService


def get_playlist_service(session: AsyncSession = Depends(get_db)) -> PlaylistService:
    return PlaylistService(session)
