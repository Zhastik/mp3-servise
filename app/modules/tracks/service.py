"""Track use cases: ownership, quota, transactions and media coordination."""
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.errors import ApplicationError
from app.core.transactions import transaction
from app.modules.favorites.repository import FavoriteRepository
from app.modules.playlists.repository import PlaylistRepository
from app.modules.tracks.models import Track
from app.modules.tracks.ports import AudioProcessor, AudioStorage, FileCleanup, FileDeletionQueue, UploadSource
from app.modules.tracks.repository import TrackRepository
from app.modules.tracks.schemas import TrackEdit, TrackPage, TrackQuery, TrackRead
from app.modules.users.repository import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class UploadLimiter:
    """Only one in-flight upload per user in this application process."""
    def __init__(self):
        self._locks: dict[int, asyncio.Lock] = {}

    @asynccontextmanager
    async def acquire(self, owner_id: int):
        lock = self._locks.setdefault(owner_id, asyncio.Lock())
        if lock.locked():
            raise ApplicationError("Дождитесь завершения предыдущей загрузки", 429)
        async with lock:
            try:
                yield
            finally:
                self._locks.pop(owner_id, None)


class TrackService:
    def __init__(self, db: "AsyncSession", processor: AudioProcessor, storage: AudioStorage,
                 cleanup: FileCleanup, limiter: UploadLimiter, deletions: FileDeletionQueue):
        self.db = db
        self.processor = processor
        self.storage = storage
        self.cleanup = cleanup
        self.limiter = limiter
        self.tracks = TrackRepository(db)
        self.favorites = FavoriteRepository(db)
        self.playlists = PlaylistRepository(db)
        self.users = UserRepository(db)
        self.deletions = deletions

    async def _require_track(self, track_id: int) -> Track:
        track = await self.tracks.get_active(track_id)
        if track is None:
            raise ApplicationError("Трек не найден", 404)
        return track

    async def list(self, query: TrackQuery, user_id: int | None) -> TrackPage:
        if (query.mine or query.favorites) and user_id is None:
            raise ApplicationError("Войдите в аккаунт", 401)
        tracks, total = await self.tracks.list(query, user_id)
        liked = await self.favorites.get_ids(user_id) if user_id is not None else set()
        return TrackPage(tracks=[TrackRead.from_track(t, liked) for t in tracks], total=total,
                         page=query.page, page_size=query.page_size)

    async def upload(self, owner_id: int, name: str, artist: str, file: UploadSource) -> TrackRead:
        try:
            if not name.strip() or not artist.strip():
                raise ApplicationError("Укажите название и исполнителя", 422)
            async with self.limiter.acquire(owner_id):
                stored = None
                try:
                    await self.users.lock_for_update(owner_id)
                    limit = settings.MAX_USER_STORAGE_MB * 1024 * 1024
                    used, count = await self.tracks.usage(owner_id)
                    if used >= limit or count >= 500:
                        raise ApplicationError(f"Лимит библиотеки: 500 треков или {settings.MAX_USER_STORAGE_MB} МБ", 413)
                    stored = await self.processor.process_upload(file)
                    if used + stored.file_size > limit:
                        raise ApplicationError(f"Лимит библиотеки: {settings.MAX_USER_STORAGE_MB} МБ", 413)
                    track = await self.tracks.create(name=name.strip(), artist=artist.strip(),
                                                     owner_id=owner_id, **asdict(stored))
                    result = TrackRead.from_track(track)
                    # A disconnected client must not cause ciphertext removal
                    # while the database commit is still completing.
                    commit = asyncio.create_task(self.db.commit())
                    try:
                        await asyncio.shield(commit)
                    except asyncio.CancelledError:
                        try:
                            await asyncio.shield(commit)
                        except asyncio.CancelledError:
                            stored = None  # Unknown outcome: preserve the bytes.
                            raise
                        else:
                            stored = None
                        raise
                    stored = None  # Committed metadata now owns the ciphertext.
                    return result
                except BaseException:
                    await self.db.rollback()
                    if stored:
                        try:
                            await self.storage.remove(stored.file_path)
                        except Exception:
                            logger.exception("Upload compensation failed; queueing ciphertext deletion")
                            try:
                                await self.deletions.enqueue(stored.file_path)
                                await self.db.commit()
                            except Exception:
                                await self.db.rollback()
                                logger.exception("Could not persist upload compensation")
                    raise
        finally:
            await file.close()

    async def update(self, owner_id: int, track_id: int, data: TrackEdit) -> TrackRead:
        async with transaction(self.db):
            track = await self._require_track(track_id)
            if track.owner_id != owner_id:
                raise ApplicationError("Изменять трек может только его владелец", 403)
            await self.tracks.update_metadata(track, data.name, data.artist)
            result = TrackRead.from_track(track, await self.favorites.get_ids(owner_id))
        return result

    async def delete(self, owner_id: int, track_id: int) -> None:
        async with transaction(self.db):
            track = await self._require_track(track_id)
            if track.owner_id != owner_id:
                raise ApplicationError("Удалять трек может только его владелец", 403)
            if track.file_path:
                await self.deletions.enqueue(track.file_path)
            await self.favorites.delete_for_track(track_id)
            await self.playlists.delete_track_references(track_id)
            await self.tracks.delete(track)
        await self.cleanup.cleanup_files()

    async def read_audio(self, track_id: int) -> bytes:
        track = await self._require_track(track_id)
        if not track.file_path:
            raise ApplicationError("Аудиофайл отсутствует", 404)
        return await self.storage.read(track.file_path)
