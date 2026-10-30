"""User queries; callers own the transaction boundary."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        return await self.session.scalar(select(User).where(User.username == username))

    async def lock_for_update(self, user_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id).with_for_update())

    async def create(self, username: str, password_hash: str) -> User:
        user = User(username=username, password_hash=password_hash)
        self.session.add(user)
        await self.session.flush()
        return user

    async def set_password(self, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        await self.session.flush()
