"""Public playlist request and response contracts."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaylistCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class PlaylistUpdate(PlaylistCreate):
    pass


class PlaylistRead(BaseModel):
    id: int
    name: str
    created_at: datetime
    track_count: int = Field(ge=0)


class PlaylistUpdateRead(BaseModel):
    id: int
    name: str
