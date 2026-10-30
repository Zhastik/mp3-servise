"""File/database consistency at the track use-case boundary, without a database."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.errors import ApplicationError
from app.modules.tracks.ports import StoredAudio
from app.modules.tracks.service import TrackService, UploadLimiter


def make_service(commit=None):
    stored = StoredAudio("/private/ciphertext.enc", "song.mp3", 128, "audio/mpeg", 2.5)
    db = SimpleNamespace(commit=commit or AsyncMock(), rollback=AsyncMock())
    source = SimpleNamespace(filename="song.mp3", read=AsyncMock(), close=AsyncMock())
    processor = SimpleNamespace(process_upload=AsyncMock(return_value=stored))
    storage = SimpleNamespace(read=AsyncMock(), remove=AsyncMock())
    cleanup = SimpleNamespace(cleanup_files=AsyncMock())
    deletions = SimpleNamespace(enqueue=AsyncMock())
    service = TrackService(db, processor, storage, cleanup, UploadLimiter(), deletions)
    track = SimpleNamespace(id=1, name="Song", artist="Artist", owner_id=7,
                            duration=stored.duration, file_size=stored.file_size,
                            created_at=datetime.now(timezone.utc))
    service.tracks = SimpleNamespace(usage=AsyncMock(return_value=(0, 0)),
                                    create=AsyncMock(return_value=track))
    service.users = SimpleNamespace(lock_for_update=AsyncMock())
    return service, source, stored


@pytest.mark.asyncio
async def test_cancelled_upload_waits_for_commit_and_keeps_committed_ciphertext():
    commit_started = asyncio.Event()
    permit_commit = asyncio.Event()
    commit_finished = asyncio.Event()

    async def commit():
        commit_started.set()
        await permit_commit.wait()
        commit_finished.set()

    service, source, stored = make_service(AsyncMock(side_effect=commit))
    upload = asyncio.create_task(service.upload(7, "Song", "Artist", source))
    await asyncio.wait_for(commit_started.wait(), timeout=2)
    upload.cancel()
    # An event-loop barrier lets the cancellation handler run; the commit gate
    # remains closed, so the assertion does not depend on elapsed wall time.
    cancellation_delivered = asyncio.Event()
    asyncio.get_running_loop().call_soon(cancellation_delivered.set)
    await cancellation_delivered.wait()
    try:
        assert not upload.done(), "Upload returned while its commit was unresolved"
        assert not commit_finished.is_set()
        service.storage.remove.assert_not_awaited()
    finally:
        permit_commit.set()
        with pytest.raises(asyncio.CancelledError):
            await upload
    assert commit_finished.is_set()
    service.storage.remove.assert_not_awaited()
    service.deletions.enqueue.assert_not_awaited()
    source.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_failure_and_storage_failure_queue_cleanup_preserving_original_error():
    commit_failure = RuntimeError("original database commit failure")
    service, source, stored = make_service(AsyncMock(side_effect=[commit_failure, None]))
    service.storage.remove.side_effect = OSError("storage temporarily unavailable")

    with pytest.raises(RuntimeError) as result:
        await service.upload(7, "Song", "Artist", source)

    assert result.value is commit_failure
    service.db.rollback.assert_awaited_once()
    service.storage.remove.assert_awaited_once_with(stored.file_path)
    service.deletions.enqueue.assert_awaited_once_with(stored.file_path)
    assert service.db.commit.await_count == 2  # track failed; deletion queue committed
    source.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_processing_failure_rolls_back_and_closes_source_without_removing_unknown_file():
    service, source, stored = make_service()
    rejection = ApplicationError("scanner rejected upload", 400)
    service.processor.process_upload.side_effect = rejection

    with pytest.raises(ApplicationError) as result:
        await service.upload(7, "Song", "Artist", source)

    assert result.value is rejection
    service.db.rollback.assert_awaited_once()
    service.db.commit.assert_not_awaited()
    service.tracks.create.assert_not_awaited()
    service.storage.remove.assert_not_awaited()
    service.deletions.enqueue.assert_not_awaited()
    source.close.assert_awaited_once()
