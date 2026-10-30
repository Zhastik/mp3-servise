"""Playlist persistence models; table names retain migration compatibility."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow


class Playlist(Base):
    __tablename__ = "playlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class PlaylistTrack(Base):
    __tablename__ = "playlisttrackmodel"
    __table_args__ = (UniqueConstraint("playlist_id", "music_id", name="uq_playlist_track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlist.id", ondelete="CASCADE"), nullable=False, index=True
    )
    music_id: Mapped[int] = mapped_column(
        ForeignKey("track.id", ondelete="CASCADE"), nullable=False, index=True
    )
