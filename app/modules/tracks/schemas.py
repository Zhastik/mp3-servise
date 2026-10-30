"""Validated catalogue inputs and public output, excluding storage internals."""
from datetime import datetime
from typing import TYPE_CHECKING, Collection

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.modules.tracks.models import Track


class TrackEdit(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)


class TrackQuery(BaseModel):
    search: str = Field(default="", max_length=200)
    mine: bool = False
    favorites: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)


class TrackRead(BaseModel):
    id: int
    name: str
    artist: str
    owner_id: int | None
    duration: float
    file_size: int
    created_at: datetime
    is_favorite: bool

    @classmethod
    def from_track(cls, track: "Track", favorites: Collection[int] = ()) -> "TrackRead":
        return cls(id=track.id, name=track.name, artist=track.artist or "Неизвестный исполнитель",
                   owner_id=track.owner_id, duration=track.duration or 0, file_size=track.file_size or 0,
                   created_at=track.created_at, is_favorite=track.id in favorites)


class TrackPage(BaseModel):
    tracks: list[TrackRead]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class UploadStatus(BaseModel):
    uploads_ready: bool
    upload_message: str
    max_upload_mb: int
