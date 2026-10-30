"""Request-scoped favorite service construction."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_depends import get_db
from app.modules.favorites.service import FavoriteService


def get_favorite_service(session: AsyncSession = Depends(get_db)) -> FavoriteService:
    return FavoriteService(session)
