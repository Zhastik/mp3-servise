"""Track queries and persistence, without transaction or access-policy decisions."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.favorites.models import Favorite
from app.modules.tracks.models import Track
from app.modules.tracks.schemas import TrackQuery


class TrackRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active(self, track_id: int) -> Track | None:
        return await self.db.scalar(select(Track).where(Track.id == track_id, Track.is_active.is_(True)))

    async def list(self, query: TrackQuery, user_id: int | None) -> tuple[list[Track], int]:
        filters = [Track.is_active.is_(True), Track.file_path.is_not(None)]
        if query.mine:
            filters.append(Track.owner_id == user_id)
        if query.favorites:
            filters.append(Track.id.in_(select(Favorite.track_id).where(Favorite.user_id == user_id)))
        if query.search.strip():
            term = "%" + query.search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            filters.append(Track.name.ilike(term, escape="\\") | Track.artist.ilike(term, escape="\\"))
        total = await self.db.scalar(select(func.count()).select_from(Track).where(*filters)) or 0
        tracks = (await self.db.scalars(select(Track).where(*filters).order_by(Track.id.desc())
                                      .offset((query.page - 1) * query.page_size).limit(query.page_size))).all()
        return list(tracks), total

    async def usage(self, owner_id: int) -> tuple[int, int]:
        used, count = (await self.db.execute(select(func.coalesce(func.sum(Track.file_size), 0), func.count())
                    .select_from(Track).where(Track.owner_id == owner_id, Track.is_active.is_(True)))).one()
        return used, count

    async def create(self, **values) -> Track:
        track = Track(**values)
        self.db.add(track)
        await self.db.flush()
        return track

    async def update_metadata(self, track: Track, name: str, artist: str) -> Track:
        track.name, track.artist = name, artist
        await self.db.flush()
        return track

    async def delete(self, track: Track) -> None:
        await self.db.delete(track)
