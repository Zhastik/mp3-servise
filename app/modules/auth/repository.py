"""Session persistence without HTTP dependencies or implicit commits."""
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Session


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_token_digest(self, token_digest: str) -> Session | None:
        return await self.session.get(Session, token_digest)

    async def revoke_by_token_digest(self, token_digest: str) -> None:
        await self.session.execute(delete(Session).where(Session.token == token_digest))

    async def remove_expired(self, now: datetime) -> None:
        await self.session.execute(delete(Session).where(Session.expires <= now))

    async def create(self, token_digest: str, user_id: int, csrf_token: str, expires: datetime) -> Session:
        session = Session(token=token_digest, user_id=user_id, csrf_token=csrf_token, expires=expires)
        self.session.add(session)
        await self.session.flush()
        return session

    async def delete(self, session: Session) -> None:
        await self.session.delete(session)
