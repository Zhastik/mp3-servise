"""Adapt cookies, bearer headers, CSRF and request throttling to auth use cases."""
from collections import OrderedDict, deque
import secrets
import time

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_depends import get_db
from app.core.errors import ApplicationError
from app.modules.auth.service import AuthService
from app.modules.users.models import User

COOKIE_NAME = "volna_session"
_attempts: OrderedDict[str, deque[float]] = OrderedDict()


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


def token_from_request(request: Request) -> tuple[str | None, bool]:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip(), False
    return request.cookies.get(COOKIE_NAME), True


async def optional_user(request: Request, service: AuthService = Depends(get_auth_service)) -> User | None:
    token, from_cookie = token_from_request(request)
    identity = await service.validate_session(token)
    if identity is None:
        return None
    user, session = identity
    request.state.auth_session = session
    if from_cookie and request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not secrets.compare_digest(session.csrf_token, supplied):
            raise ApplicationError("Обновите страницу и повторите действие.", 403)
    return user


async def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise ApplicationError("Войдите в аккаунт.", 401, {"WWW-Authenticate": "Bearer"})
    return user


async def throttle(request: Request) -> None:
    # Per-process by design; a multi-worker deployment needs a shared limiter.
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _attempts.setdefault(key, deque())
    _attempts.move_to_end(key)
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= 10:
        raise ApplicationError("Слишком много попыток. Попробуйте через минуту.", 429, {"Retry-After": "60"})
    bucket.append(now)
    while len(_attempts) > 10000:
        _attempts.popitem(last=False)
