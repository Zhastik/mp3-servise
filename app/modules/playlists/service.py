"""Playlist use cases, ownership rules and transaction boundaries."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.transactions import transaction
from app.modules.favorites.repository import FavoriteRepository
from app.modules.playlists.models import Playlist
from app.modules.playlists.repository import PlaylistRepository
from app.modules.playlists.schemas import PlaylistCreate, PlaylistRead, PlaylistUpdate, PlaylistUpdateRead
from app.modules.tracks.repository import TrackRepository
from app.modules.tracks.schemas import TrackPage, TrackRead


class PlaylistService:
    MAX_PLAYLISTS = 100

    def __init__(self, session: AsyncSession):
        self.session = session
        self.playlists = PlaylistRepository(session)
        self.tracks = TrackRepository(session)
        self.favorites = FavoriteRepository(session)

    async def _require_owned(self, owner_id: int, playlist_id: int) -> Playlist:
        playlist = await self.playlists.get_owned(playlist_id, owner_id)
        if playlist is None:
            raise ApplicationError("Плейлист не найден", 404)
        return playlist

    async def list(self, owner_id: int) -> list[PlaylistRead]:
        return [
            PlaylistRead(id=playlist.id, name=playlist.name, created_at=playlist.created_at, track_count=count)
            for playlist, count in await self.playlists.list_owned(owner_id)
        ]

    async def create(self, owner_id: int, data: PlaylistCreate) -> PlaylistRead:
        async with transaction(self.session):
            if await self.playlists.count_owned(owner_id) >= self.MAX_PLAYLISTS:
                raise ApplicationError("Можно создать до 100 плейлистов", 400)
            playlist = await self.playlists.create(owner_id, data.name)
            result = PlaylistRead(id=playlist.id, name=playlist.name, created_at=playlist.created_at, track_count=0)
        return result

    async def update(self, owner_id: int, playlist_id: int, data: PlaylistUpdate) -> PlaylistUpdateRead:
        async with transaction(self.session):
            playlist = await self._require_owned(owner_id, playlist_id)
            await self.playlists.rename(playlist, data.name)
            result = PlaylistUpdateRead(id=playlist.id, name=playlist.name)
        return result

    async def delete(self, owner_id: int, playlist_id: int) -> None:
        async with transaction(self.session):
            playlist = await self._require_owned(owner_id, playlist_id)
            await self.playlists.delete(playlist)

    async def list_tracks(self, owner_id: int, playlist_id: int) -> TrackPage:
        await self._require_owned(owner_id, playlist_id)
        tracks = await self.playlists.list_tracks(playlist_id)
        favorites = await self.favorites.get_ids(owner_id)
        return TrackPage(
            tracks=[TrackRead.from_track(track, favorites) for track in tracks],
            total=len(tracks), page=1, page_size=max(1, len(tracks)),
        )

    async def add_track(self, owner_id: int, playlist_id: int, track_id: int) -> None:
        async with transaction(self.session):
            await self._require_owned(owner_id, playlist_id)
            if await self.tracks.get_active(track_id) is None:
                raise ApplicationError("Трек не найден", 404)
            await self.playlists.add_track(playlist_id, track_id)

    async def remove_track(self, owner_id: int, playlist_id: int, track_id: int) -> None:
        async with transaction(self.session):
            await self._require_owned(owner_id, playlist_id)
            await self.playlists.remove_track(playlist_id, track_id)
