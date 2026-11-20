from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.deps import current_user
from app.auth.tokens import make_access
from app.campaigns.sync import sync_after_login
from app.config import get_settings
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    login: str
    password: str


def _set_cookies(response: Response, user_id: int, refresh: str) -> None:
    s = get_settings()
    common = {"httponly": True, "samesite": "lax", "secure": s.cookie_secure}
    response.set_cookie(
        "access_token",
        make_access(user_id),
        max_age=s.access_ttl_min * 60,
        path="/api",
        **common,
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        max_age=s.refresh_ttl_days * 86400,
        path="/api/auth",
        **common,
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/api")
    response.delete_cookie("refresh_token", path="/api/auth")


@router.post("/login", status_code=204)
async def login(
    body: LoginIn,
    response: Response,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> None:
    user = await service.authenticate(session, body.login, body.password)
    if user is None:
        raise HTTPException(401, "Invalid login or password")
    _set_cookies(response, user.id, await service.issue_refresh(session, user.id))
    background.add_task(sync_after_login)


@router.post("/refresh", status_code=204)
async def refresh(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> None:
    token = request.cookies.get("refresh_token")
    result = await service.rotate_refresh(session, token) if token else None
    if result is None:
        raise HTTPException(401, "Invalid refresh token")
    user_id, new_token = result
    if await session.get(User, user_id) is None:
        raise HTTPException(401, "Invalid refresh token")
    _set_cookies(response, user_id, new_token)


@router.post("/logout", status_code=204)
async def logout(
    request: Request, response: Response, session: AsyncSession = Depends(get_session)
) -> None:
    token = request.cookies.get("refresh_token")
    if token:
        await service.revoke(session, token)
    _clear_cookies(response)


@router.get("/me")
async def me(
    user_id: int = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return {"login": user.login}
