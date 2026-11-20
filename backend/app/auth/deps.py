from fastapi import HTTPException, Request

from app.auth.tokens import InvalidToken, read_access


def current_user(request: Request) -> int:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated") from None
    try:
        return read_access(token)
    except InvalidToken:
        raise HTTPException(401, "Not authenticated") from None
