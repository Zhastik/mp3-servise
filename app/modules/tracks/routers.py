"""HTTP contract for the music catalogue; business decisions live in TrackService."""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response

from app.api.responses import build_audio_response
from app.modules.auth.dependencies import current_user, optional_user
from app.modules.tracks.dependencies import get_track_service
from app.modules.tracks.schemas import TrackEdit, TrackPage, TrackQuery, TrackRead
from app.modules.tracks.service import TrackService
from app.modules.users.models import User

router = APIRouter(prefix="/tracks", tags=["Tracks"])


@router.get("", response_model=TrackPage)
async def list_tracks(query: Annotated[TrackQuery, Query()], user: User | None = Depends(optional_user),
                      service: TrackService = Depends(get_track_service)) -> TrackPage:
    return await service.list(query, user.id if user else None)


@router.post("", response_model=TrackRead, status_code=201)
async def upload_track(name: str = Form(..., min_length=1, max_length=200),
                       artist: str = Form(..., min_length=1, max_length=200),
                       file: UploadFile = File(...), user: User = Depends(current_user),
                       service: TrackService = Depends(get_track_service)) -> TrackRead:
    return await service.upload(user.id, name, artist, file)


@router.patch("/{track_id}", response_model=TrackRead)
async def update_track(track_id: int, data: TrackEdit, user: User = Depends(current_user),
                       service: TrackService = Depends(get_track_service)) -> TrackRead:
    return await service.update(user.id, track_id, data)


@router.delete("/{track_id}", status_code=204)
async def delete_track(track_id: int, user: User = Depends(current_user),
                       service: TrackService = Depends(get_track_service)) -> Response:
    await service.delete(user.id, track_id)
    return Response(status_code=204)


@router.api_route("/{track_id}/stream", methods=["GET", "HEAD"])
async def stream_track(track_id: int, request: Request,
                       service: TrackService = Depends(get_track_service)) -> Response:
    data = await service.read_audio(track_id)
    return build_audio_response(data, request.headers.get("range"), request.method == "HEAD")
