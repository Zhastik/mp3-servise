"""Favorite persistence; idempotent inserts use a savepoint, never a commit."""
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.favorites.models import Favorite


class FavoriteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_ids(self, user_id: int) -> set[int]:
        statement = select(Favorite.track_id).where(Favorite.user_id == user_id)
        return set((await self.session.scalars(statement)).all())

    async def get_id(self, user_id: int, track_id: int) -> int | None:
        return await self.session.scalar(
            select(Favorite.id).where(Favorite.user_id == user_id, Favorite.track_id == track_id)
        )

    async def add(self, user_id: int, track_id: int) -> None:
        if await self.get_id(user_id, track_id) is not None:
            return
        try:
            async with self.session.begin_nested():
                self.session.add(Favorite(user_id=user_id, track_id=track_id))
                await self.session.flush()
        except IntegrityError:
            if await self.get_id(user_id, track_id) is None:
                raise

    async def remove(self, user_id: int, track_id: int) -> None:
        await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.track_id == track_id)
        )

    async def delete_for_track(self, track_id: int) -> None:
        """Remove favorites inside the caller's track-deletion transaction."""
        await self.session.execute(delete(Favorite).where(Favorite.track_id == track_id))
