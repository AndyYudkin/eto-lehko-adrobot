from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.auth.deps import current_user
from app.auth.router import router as auth_router
from app.auth.service import seed_user
from app.config import get_settings
from app.creator.router import router as campaigns_router
from app.db import Base, async_session, engine
from app.editor.router import router as editor_router
from app.errors import register_error_handlers
from app.offers.router import router as offers_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # no migrations: the app is deployed once on a clean DB, so create the
    # tables at startup; after a schema change recreate the DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    s = get_settings()
    async with async_session() as session:
        await seed_user(session, s.app_login, s.app_password)
    yield


app = FastAPI(lifespan=lifespan)
register_error_handlers(app)

# every application router goes in here; unlisted paths are closed by default
protected = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

protected.include_router(campaigns_router)
protected.include_router(offers_router)
protected.include_router(editor_router)

app.include_router(auth_router)
app.include_router(protected)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
