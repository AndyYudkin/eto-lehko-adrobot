from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import (
    db,
    models,  # noqa: F401  (registers tables on Base.metadata)
)
from app.auth.service import seed_user
from app.config import get_settings
from app.db import Base, get_session
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def engine():
    url = get_settings().test_database_url
    assert url, "TEST_DATABASE_URL is not set"
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
def _isolate_app(engine, monkeypatch):
    # background tasks (sync_offers_safe) open sessions via db.async_session:
    # point it at the test DB; Keitaro is "not configured" unless a test sets it
    monkeypatch.setattr(
        db, "async_session", async_sessionmaker(engine, expire_on_commit=False)
    )
    s = get_settings()
    monkeypatch.setattr(s, "kt_url", None)
    monkeypatch.setattr(s, "kt_api_key", None)


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def client(engine) -> AsyncIterator[httpx.AsyncClient]:
    async def override() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


TEST_LOGIN = "admin"
TEST_PASSWORD = "test-password"


@pytest_asyncio.fixture
async def auth_client(client, session) -> httpx.AsyncClient:
    await seed_user(session, TEST_LOGIN, TEST_PASSWORD)
    r = await client.post(
        "/api/auth/login", json={"login": TEST_LOGIN, "password": TEST_PASSWORD}
    )
    assert r.status_code == 204
    return client
