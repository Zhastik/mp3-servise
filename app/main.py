"""Composition root for the VOLNA application."""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.router import router
from app.core.config import BASE_DIR, settings
from app.core.middleware import SecurityMiddleware
from app.lifespan import lifespan


def create_app() -> FastAPI:
    application = FastAPI(title="VOLNA · Музыкальный сервис", version="1.0.0", lifespan=lifespan)
    register_exception_handlers(application)
    application.add_middleware(SecurityMiddleware)
    application.add_middleware(TrustedHostMiddleware,
        allowed_hosts=[h.strip() for h in settings.ALLOWED_HOSTS.split(",") if h.strip()])
    application.include_router(router)
    application.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

    @application.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(BASE_DIR / "app" / "static" / "index.html", headers={"Cache-Control": "no-cache"})

    return application


app = create_app()
