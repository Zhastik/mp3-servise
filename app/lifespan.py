"""Application lifecycle: initialize adapters and own background workers."""
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import async_engine, initialize_database
from app.infrastructure.media.cleanup import cleanup_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    settings.encryption_key()
    await initialize_database()
    cleaner = asyncio.create_task(cleanup_worker(), name="ciphertext-cleanup")
    try:
        yield
    finally:
        cleaner.cancel()
        with suppress(asyncio.CancelledError):
            await cleaner
        await async_engine.dispose()
