"""Favorite use cases and transaction boundaries."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.transactions import transaction
from app.modules.favorites.repository import FavoriteRepository
from app.modules.tracks.repository import TrackRepository


class FavoriteService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.favorites = FavoriteRepository(session)
        self.tracks = TrackRepository(session)

    async def favorite(self, owner_id: int, track_id: int) -> None:
        async with transaction(self.session):
            if await self.tracks.get_active(track_id) is None:
                raise ApplicationError("Трек не найден", 404)
            await self.favorites.add(owner_id, track_id)

    async def unfavorite(self, owner_id: int, track_id: int) -> None:
        async with transaction(self.session):
            await self.favorites.remove(owner_id, track_id)
