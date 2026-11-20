import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings


class InvalidToken(Exception):
    pass


def make_access(user_id: int) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.access_ttl_min)
    return jwt.encode(
        {"sub": str(user_id), "exp": exp}, s.jwt_secret, algorithm="HS256"
    )


def read_access(token: str) -> int:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise InvalidToken from e


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_refresh(token)
