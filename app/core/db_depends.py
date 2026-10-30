from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session_marker

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_marker() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
