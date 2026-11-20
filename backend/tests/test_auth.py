from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select, update

from app.auth import service
from app.auth.service import REFRESH_REUSE_GRACE_SEC, seed_user
from app.config import get_settings
from app.main import app
from app.models import RefreshToken, User


async def _users(session):
    return (await session.execute(select(User))).scalars().all()


async def _login(client, login="admin", password="pw"):
    return await client.post(
        "/api/auth/login", json={"login": login, "password": password}
    )


async def test_seed_user(session):
    await seed_user(session, "admin", "pw")
    users = await _users(session)
    assert len(users) == 1
    assert users[0].password_hash != "pw"
    assert bcrypt.checkpw(b"pw", users[0].password_hash.encode())

    await seed_user(session, "admin", "pw2")
    users = await _users(session)
    assert len(users) == 1
    h = users[0].password_hash.encode()
    assert bcrypt.checkpw(b"pw2", h)
    assert not bcrypt.checkpw(b"pw", h)

    await seed_user(session, "root", "pw")
    assert [u.login for u in await _users(session)] == ["root"]


async def test_login(client, session):
    await seed_user(session, "admin", "pw")
    r = await _login(client)
    assert r.status_code == 204
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("httponly" in c.lower() for c in cookies)
    assert any("access_token=" in c and "Path=/api;" in c + ";" for c in cookies)
    assert any("refresh_token=" in c and "Path=/api/auth" in c for c in cookies)

    me = await client.get("/api/auth/me")
    assert me.json() == {"login": "admin"}

    stored = (await session.execute(select(RefreshToken))).scalar_one()
    assert stored.token_hash != client.cookies.get("refresh_token")

    bad_pw = await _login(client, password="nope")
    bad_user = await _login(client, login="nobody")
    assert bad_pw.status_code == bad_user.status_code == 401
    assert bad_pw.json()["detail"] == bad_user.json()["detail"]


async def test_access_expired_then_refresh(client, session):
    await seed_user(session, "admin", "pw")
    await _login(client)
    user = (await _users(session))[0]
    old_refresh = client.cookies.get("refresh_token")

    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    client.cookies.set("access_token", expired, domain="test.local", path="/api")
    assert (await client.get("/api/auth/me")).status_code == 401

    r = await client.post("/api/auth/refresh")
    assert r.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 200
    assert client.cookies.get("refresh_token") != old_refresh

    session.expire_all()
    rows = (await session.execute(select(RefreshToken))).scalars().all()
    assert len(rows) == 2
    assert sum(1 for t in rows if t.revoked_at is not None) == 1


async def test_refresh_reuse_revokes_all(client, session):
    await seed_user(session, "admin", "pw")
    await _login(client)
    r1 = client.cookies.get("refresh_token")
    assert (await client.post("/api/auth/refresh")).status_code == 204

    r2 = client.cookies.get("refresh_token")

    # past the grace window, reuse of R1 means a leak
    old = datetime.now(UTC) - timedelta(seconds=REFRESH_REUSE_GRACE_SEC + 1)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.revoked_at.is_not(None))
        .values(revoked_at=old)
    )
    await session.commit()

    client.cookies.set("refresh_token", r1, domain="test.local", path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401

    # every refresh of the user is gone, R2 included
    session.expire_all()
    assert (await session.execute(select(RefreshToken))).scalars().all() == []
    client.cookies.set("refresh_token", r2, domain="test.local", path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_concurrent_refresh_within_grace(client, session):
    # two tabs refresh with the same token at once: both must stay logged in
    await seed_user(session, "admin", "pw")
    await _login(client)
    r1 = client.cookies.get("refresh_token")
    assert (await client.post("/api/auth/refresh")).status_code == 204
    r2 = client.cookies.get("refresh_token")

    client.cookies.set("refresh_token", r1, domain="test.local", path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 204

    client.cookies.set("refresh_token", r2, domain="test.local", path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 204


async def test_unknown_login_still_runs_bcrypt(client, session, monkeypatch):
    # same work for unknown login and wrong password: no timing hint
    await seed_user(session, "admin", "pw")
    calls = []
    real = service.bcrypt.checkpw

    def spy(password, hashed):
        calls.append(1)
        return real(password, hashed)

    monkeypatch.setattr(service.bcrypt, "checkpw", spy)
    r = await _login(client, login="nobody", password="pw")
    assert r.status_code == 401
    assert calls == [1]


async def test_logout(client, session):
    await seed_user(session, "admin", "pw")
    await _login(client)
    refresh = client.cookies.get("refresh_token")
    r = await client.post("/api/auth/logout")
    assert r.status_code == 204
    assert all(
        "max-age=0" in c.lower() or "1970" in c
        for c in r.headers.get_list("set-cookie")
    )
    client.cookies.set("refresh_token", refresh, domain="test.local", path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_all_routes_protected(client):
    paths = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            continue
        if path.startswith("/api/auth") or path == "/api/health":
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            paths.add((method, path))
    for method, path in paths:
        r = await client.request(method, path)
        assert r.status_code == 401, (method, path)


async def test_deleted_user_cannot_refresh(client, session):
    await seed_user(session, "admin", "pw")
    await _login(client)
    await seed_user(session, "root", "pw")
    assert (await client.post("/api/auth/refresh")).status_code == 401
