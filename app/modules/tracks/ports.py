"""Capabilities required by track use cases, implemented by media adapters."""
from dataclasses import dataclass
from typing import Protocol


class UploadSource(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class StoredAudio:
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    duration: float


class AudioProcessor(Protocol):
    async def process_upload(self, file: UploadSource) -> StoredAudio: ...
    async def status(self) -> dict: ...


class AudioStorage(Protocol):
    async def read(self, filename: str) -> bytes: ...
    async def remove(self, filename: str) -> None: ...


class FileCleanup(Protocol):
    async def cleanup_files(self) -> None: ...


class FileDeletionQueue(Protocol):
    async def enqueue(self, path: str) -> None: ...
