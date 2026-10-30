"""Public route composition; prefixes are declared exactly once."""
from fastapi import APIRouter

from app.api.system import router as system_router
from app.modules.auth.routers import router as auth_router
from app.modules.favorites.routers import router as favorites_router
from app.modules.playlists.routers import router as playlists_router
from app.modules.tracks.routers import router as tracks_router

api_router = APIRouter(prefix="/api")
api_router.include_router(tracks_router)
api_router.include_router(favorites_router)
api_router.include_router(playlists_router)

router = APIRouter()
router.include_router(auth_router)
router.include_router(api_router)
router.include_router(system_router)
