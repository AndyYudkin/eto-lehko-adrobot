from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_refresh, new_refresh
from app.config import get_settings
from app.models import RefreshToken, User

# A refresh token rotated less than this many seconds ago may be used again:
# two tabs refreshing at once send the same token. Older reuse means a leak.
REFRESH_REUSE_GRACE_SEC = 10

# Checked against for an unknown login, so it costs the same bcrypt work as a
# wrong password and response time doesn't reveal which logins exist.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


async def seed_user(session: AsyncSession, login: str, password: str) -> None:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # other users go away; their refresh tokens cascade (ON DELETE CASCADE)
    await session.execute(delete(User).where(User.login != login))
    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()
    if user:
        user.password_hash = password_hash
    else:
        session.add(User(login=login, password_hash=password_hash))
    await session.commit()


async def authenticate(session: AsyncSession, login: str, password: str) -> User | None:
    user = (
        await session.execute(select(User).where(User.login == login))
    ).scalar_one_or_none()
    if user is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        return None
    if bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        return user
    return None


async def issue_refresh(session: AsyncSession, user_id: int) -> str:
    token, token_hash = new_refresh()
    expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_ttl_days)
    session.add(
        RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires)
    )
    await session.commit()
    return token


async def rotate_refresh(session: AsyncSession, token: str) -> tuple[int, str] | None:
    """Return (user_id, new refresh token), or None if the token is unusable.

    `revoked_at` is set only by rotation; logout and leak handling delete rows,
    so a revoked row always means "already rotated".
    """
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(token))
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    if row.expires_at <= now:
        return None
    if row.revoked_at is not None:
        if now - row.revoked_at > timedelta(seconds=REFRESH_REUSE_GRACE_SEC):
            # old rotated token came back: assume leak, end every session
            await revoke_all(session, row.user_id)
            return None
        # concurrent refresh from another tab: allow, issue a fresh token
        return row.user_id, await issue_refresh(session, row.user_id)
    row.revoked_at = now
    await session.commit()
    return row.user_id, await issue_refresh(session, row.user_id)


async def revoke_all(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await session.commit()


async def revoke(session: AsyncSession, token: str) -> None:
    await session.execute(
        delete(RefreshToken).where(RefreshToken.token_hash == hash_refresh(token))
    )
    await session.commit()
