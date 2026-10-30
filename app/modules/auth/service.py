"""Authentication use cases and their transaction boundaries."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.errors import ApplicationError
from app.core.transactions import transaction
from app.modules.auth.models import Session
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import Credentials
from app.modules.auth.security import SCRYPT_N, decode_password, derive_password, encode_password, token_digest
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


@dataclass(frozen=True)
class AuthenticationResult:
    user: User
    session: Session
    token: str


class AuthService:
    def __init__(self, db: AsyncSession, config: Settings = settings):
        self.db = db
        self.config = config
        self.users = UserRepository(db)
        self.sessions = AuthRepository(db)

    async def validate_session(self, token: str | None) -> tuple[User, Session] | None:
        if not token or len(token) > 256:
            return None
        session = await self.sessions.get_by_token_digest(token_digest(token))
        if session is None:
            return None
        expires = session.expires
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return None
        user = await self.users.get_by_id(session.user_id)
        return (user, session) if user is not None else None

    async def register(self, data: Credentials, old_token: str | None = None) -> AuthenticationResult:
        salt = secrets.token_hex(16)
        hashed = await derive_password(data.password, salt)
        async with transaction(self.db):
            try:
                user = await self.users.create(data.username, encode_password(salt, hashed))
            except IntegrityError as exc:
                raise ApplicationError("Это имя пользователя уже занято.", 409) from exc
            return await self._create_session(user, old_token)

    async def login(self, data: Credentials, old_token: str | None = None) -> AuthenticationResult:
        async with transaction(self.db):
            user = await self.users.get_by_username(data.username)
            try:
                salt, expected, n = decode_password(user.password_hash) if user else ("00" * 16, "0" * 128, SCRYPT_N)
            except (ValueError, TypeError):
                raise ApplicationError("Неверное имя пользователя или пароль.", 401)
            actual = await derive_password(data.password, salt, n)
            if user is None or not secrets.compare_digest(expected, actual):
                raise ApplicationError("Неверное имя пользователя или пароль.", 401)
            if n != SCRYPT_N:
                upgraded = await derive_password(data.password, salt)
                await self.users.set_password(user, encode_password(salt, upgraded))
            return await self._create_session(user, old_token)

    async def _create_session(self, user: User, old_token: str | None) -> AuthenticationResult:
        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        if old_token:
            await self.sessions.revoke_by_token_digest(token_digest(old_token))
        await self.sessions.remove_expired(now)
        session = await self.sessions.create(
            token_digest(token), user.id, secrets.token_urlsafe(32),
            now + timedelta(hours=self.config.SESSION_HOURS),
        )
        return AuthenticationResult(user=user, session=session, token=token)

    async def logout(self, session: Session) -> None:
        async with transaction(self.db):
            await self.sessions.delete(session)
