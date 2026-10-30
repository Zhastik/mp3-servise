"""HTTP favorite endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.modules.auth.dependencies import current_user
from app.modules.favorites.dependencies import get_favorite_service
from app.modules.favorites.service import FavoriteService
from app.modules.users.models import User

router = APIRouter(prefix="/tracks", tags=["Favorites"])
AuthenticatedUser = Annotated[User, Depends(current_user)]
Service = Annotated[FavoriteService, Depends(get_favorite_service)]


@router.put("/{track_id}/favorite", status_code=204, response_class=Response)
async def favorite_track(track_id: int, user: AuthenticatedUser, service: Service) -> Response:
    await service.favorite(user.id, track_id)
    return Response(status_code=204)


@router.delete("/{track_id}/favorite", status_code=204, response_class=Response)
async def unfavorite_track(track_id: int, user: AuthenticatedUser, service: Service) -> Response:
    await service.unfavorite(user.id, track_id)
    return Response(status_code=204)
