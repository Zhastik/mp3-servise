"""SQL operations for playlists; transaction boundaries belong to the service."""
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.playlists.models import Playlist, PlaylistTrack
from app.modules.tracks.models import Track


class PlaylistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, playlist_id: int, owner_id: int) -> Playlist | None:
        return await self.session.scalar(
            select(Playlist).where(
                Playlist.id == playlist_id,
                Playlist.owner_id == owner_id,
                Playlist.is_active.is_(True),
            )
        )

    async def count_owned(self, owner_id: int) -> int:
        statement = select(func.count()).select_from(Playlist).where(Playlist.owner_id == owner_id)
        return int(await self.session.scalar(statement) or 0)

    async def list_owned(self, owner_id: int) -> list[tuple[Playlist, int]]:
        track_count = (
            select(func.count(PlaylistTrack.id))
            .join(Track, Track.id == PlaylistTrack.music_id)
            .where(PlaylistTrack.playlist_id == Playlist.id, Track.is_active.is_(True))
            .correlate(Playlist)
            .scalar_subquery()
        )
        statement = (
            select(Playlist, track_count)
            .where(Playlist.owner_id == owner_id, Playlist.is_active.is_(True))
            .order_by(Playlist.id.desc())
        )
        return [(playlist, count) for playlist, count in (await self.session.execute(statement)).all()]

    async def create(self, owner_id: int, name: str) -> Playlist:
        playlist = Playlist(owner_id=owner_id, name=name)
        self.session.add(playlist)
        await self.session.flush()
        return playlist

    async def rename(self, playlist: Playlist, name: str) -> None:
        playlist.name = name
        await self.session.flush()

    async def delete(self, playlist: Playlist) -> None:
        await self.session.execute(
            delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id)
        )
        await self.session.delete(playlist)
        await self.session.flush()

    async def list_tracks(self, playlist_id: int) -> list[Track]:
        statement = (
            select(Track)
            .join(PlaylistTrack, PlaylistTrack.music_id == Track.id)
            .where(
                PlaylistTrack.playlist_id == playlist_id,
                Track.is_active.is_(True),
                Track.file_path.is_not(None),
            )
            .order_by(PlaylistTrack.id)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_track_link(self, playlist_id: int, track_id: int) -> int | None:
        return await self.session.scalar(
            select(PlaylistTrack.id).where(
                PlaylistTrack.playlist_id == playlist_id, PlaylistTrack.music_id == track_id
            )
        )

    async def add_track(self, playlist_id: int, track_id: int) -> None:
        if await self.get_track_link(playlist_id, track_id) is not None:
            return
        try:
            async with self.session.begin_nested():
                self.session.add(PlaylistTrack(playlist_id=playlist_id, music_id=track_id))
                await self.session.flush()
        except IntegrityError:
            # A concurrent identical PUT is successful; unrelated failures propagate.
            if await self.get_track_link(playlist_id, track_id) is None:
                raise

    async def remove_track(self, playlist_id: int, track_id: int) -> None:
        await self.session.execute(
            delete(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id, PlaylistTrack.music_id == track_id
            )
        )

    async def delete_track_references(self, track_id: int) -> None:
        """Remove collection links inside the caller's track-deletion transaction."""
        await self.session.execute(delete(PlaylistTrack).where(PlaylistTrack.music_id == track_id))
