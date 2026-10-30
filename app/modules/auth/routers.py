"""HTTP authentication endpoints; no database queries or password processing."""
from fastapi import APIRouter, Depends, Request, Response

from app.core.config import settings
from app.modules.auth.dependencies import COOKIE_NAME, current_user, get_auth_service, throttle, token_from_request
from app.modules.auth.schemas import AuthUser, Credentials, LogoutResult
from app.modules.auth.service import AuthenticationResult, AuthService
from app.modules.users.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _finish_login(response: Response, result: AuthenticationResult) -> AuthUser:
    response.set_cookie(
        COOKIE_NAME, result.token, max_age=settings.SESSION_HOURS * 3600,
        httponly=True, secure=settings.cookie_secure, samesite="lax", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AuthUser(id=result.user.id, username=result.user.username, csrf_token=result.session.csrf_token)


@router.post("/register", status_code=201, response_model=AuthUser, dependencies=[Depends(throttle)])
async def register(data: Credentials, request: Request, response: Response,
                   service: AuthService = Depends(get_auth_service)) -> AuthUser:
    old_token, _ = token_from_request(request)
    return _finish_login(response, await service.register(data, old_token))


@router.post("/login", response_model=AuthUser, dependencies=[Depends(throttle)])
async def login(data: Credentials, request: Request, response: Response,
                service: AuthService = Depends(get_auth_service)) -> AuthUser:
    old_token, _ = token_from_request(request)
    return _finish_login(response, await service.login(data, old_token))


@router.get("/me", response_model=AuthUser)
async def me(request: Request, response: Response, user: User = Depends(current_user)) -> AuthUser:
    response.headers["Cache-Control"] = "no-store"
    return AuthUser(id=user.id, username=user.username, csrf_token=request.state.auth_session.csrf_token)


@router.post("/logout", response_model=LogoutResult)
async def logout(request: Request, response: Response, user: User = Depends(current_user),
                 service: AuthService = Depends(get_auth_service)) -> LogoutResult:
    await service.logout(request.state.auth_session)
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return LogoutResult()
