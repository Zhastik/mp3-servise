"""HTTP endpoints for private playlists. Business rules live in PlaylistService."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.modules.auth.dependencies import current_user
from app.modules.playlists.dependencies import get_playlist_service
from app.modules.playlists.schemas import PlaylistCreate, PlaylistRead, PlaylistUpdate, PlaylistUpdateRead
from app.modules.playlists.service import PlaylistService
from app.modules.tracks.schemas import TrackPage
from app.modules.users.models import User

router = APIRouter(prefix="/playlists", tags=["Playlists"])
AuthenticatedUser = Annotated[User, Depends(current_user)]
Service = Annotated[PlaylistService, Depends(get_playlist_service)]


@router.get("", response_model=list[PlaylistRead])
async def list_playlists(user: AuthenticatedUser, service: Service) -> list[PlaylistRead]:
    return await service.list(user.id)


@router.post("", response_model=PlaylistRead, status_code=201)
async def create_playlist(data: PlaylistCreate, user: AuthenticatedUser, service: Service) -> PlaylistRead:
    return await service.create(user.id, data)


@router.patch("/{playlist_id}", response_model=PlaylistUpdateRead)
async def update_playlist(playlist_id: int, data: PlaylistUpdate, user: AuthenticatedUser, service: Service) -> PlaylistUpdateRead:
    return await service.update(user.id, playlist_id, data)


@router.delete("/{playlist_id}", status_code=204, response_class=Response)
async def delete_playlist(playlist_id: int, user: AuthenticatedUser, service: Service) -> Response:
    await service.delete(user.id, playlist_id)
    return Response(status_code=204)


@router.get("/{playlist_id}/tracks", response_model=TrackPage)
async def list_playlist_tracks(playlist_id: int, user: AuthenticatedUser, service: Service) -> TrackPage:
    return await service.list_tracks(user.id, playlist_id)


@router.put("/{playlist_id}/tracks/{track_id}", status_code=204, response_class=Response)
async def add_playlist_track(playlist_id: int, track_id: int, user: AuthenticatedUser, service: Service) -> Response:
    await service.add_track(user.id, playlist_id, track_id)
    return Response(status_code=204)


@router.delete("/{playlist_id}/tracks/{track_id}", status_code=204, response_class=Response)
async def remove_playlist_track(playlist_id: int, track_id: int, user: AuthenticatedUser, service: Service) -> Response:
    await service.remove_track(user.id, playlist_id, track_id)
    return Response(status_code=204)
