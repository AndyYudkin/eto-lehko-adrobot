import logging
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.keitaro.client import KeitaroClient, KeitaroError, get_kt
from app.models import Offer

log = logging.getLogger(__name__)


def _parse_offers(items: object) -> list[tuple[int, str, str]]:
    """Validate Keitaro's offers payload; raise KeitaroError on anything odd."""
    if not isinstance(items, list):
        raise KeitaroError(0, f"offers: expected a list, got {type(items).__name__}")
    parsed = []
    for i, o in enumerate(items):
        ok = (
            isinstance(o, dict)
            and isinstance(o.get("id"), int)
            and not isinstance(o.get("id"), bool)
            and isinstance(o.get("name"), str)
            and isinstance(o.get("state"), str)
        )
        if not ok:
            raise KeitaroError(0, f"offers[{i}]: need int id, str name, str state")
        parsed.append((o["id"], o["name"], o["state"]))
    return parsed


async def sync_offers(session: AsyncSession, kt: KeitaroClient) -> None:
    # fetch and validate everything before touching the DB
    offers = _parse_offers(await kt.list_offers())
    now = datetime.now(UTC)
    rows = [
        {"kt_id": kt_id, "name": name, "state": state, "synced_at": now}
        for kt_id, name, state in offers
    ]
    if rows:
        stmt = insert(Offer).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Offer.kt_id],
            set_={
                "name": stmt.excluded.name,
                "state": stmt.excluded.state,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)
    await session.execute(
        delete(Offer).where(Offer.kt_id.not_in([r["kt_id"] for r in rows]))
    )
    await session.commit()


async def sync_offers_safe() -> None:
    try:
        async with db.async_session() as session:
            await sync_offers(session, get_kt())
    except KeitaroError as e:
        log.warning("Offer sync skipped: Keitaro status=%s: %s", e.status, e.body[:200])
    except Exception as e:  # background task: never let it crash with a traceback
        log.warning("Offer sync failed: %s: %s", type(e).__name__, str(e)[:200])
