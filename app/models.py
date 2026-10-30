"""Explicit ORM model registry for Alembic and metadata discovery.

Entity definitions belong to their modules; application code imports them there.
Importing this registry registers every existing table with Base.metadata.
"""
from app.infrastructure.media.models import FileDeletion
from app.modules.auth.models import Session
from app.modules.favorites.models import Favorite
from app.modules.playlists.models import Playlist, PlaylistTrack
from app.modules.tracks.models import Author, Track
from app.modules.users.models import User

__all__ = ["Author", "Favorite", "FileDeletion", "Playlist", "PlaylistTrack", "Session", "Track", "User"]
