import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.keitaro.client import KeitaroClient, KeitaroError, KeitaroNotFound, get_kt
from app.models import Campaign, Offer, Stream, StreamOffer
from app.offers.sync import sync_offers_safe

log = logging.getLogger(__name__)


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def parse_streams(items: list[dict]) -> list[dict]:
    """Validate Keitaro's streams payload; raise KeitaroError on anything odd."""
    for i, s in enumerate(items):
        offers = s.get("offers")
        ok = (
            _is_int(s.get("id"))
            and _is_int(s.get("position"))
            and isinstance(offers, list)
            and all(
                isinstance(o, dict)
                and _is_int(o.get("offer_id"))
                and _is_int(o.get("share"))
                for o in offers
            )
        )
        if not ok:
            raise KeitaroError(
                0,
                f"streams[{i}]: need int id, int position, offers with int"
                " offer_id/share",
            )
    return items


async def sync_campaign(
    session: AsyncSession, kt: KeitaroClient, campaign: Campaign
) -> None:
    try:
        await kt.get_campaign(campaign.kt_id)
        items = parse_streams(await kt.get_campaign_streams(campaign.kt_id))
    except KeitaroNotFound:
        campaign.kt_deleted = True
        await session.commit()
        return

    existing = {
        s.kt_id: s
        for s in await session.scalars(
            select(Stream).where(Stream.campaign_id == campaign.id)
        )
    }
    kt_ids = {s["id"] for s in items}
    gone = [s.id for k, s in existing.items() if k not in kt_ids]
    if gone:
        await session.execute(delete(Stream).where(Stream.id.in_(gone)))

    wanted = {
        o["offer_id"] for s in items for o in s["offers"] if o.get("state") == "active"
    }
    names = {
        o.kt_id: o.name
        for o in await session.scalars(select(Offer).where(Offer.kt_id.in_(wanted)))
    }

    for item in items:
        offers = item["offers"]
        schema = item.get("schema") or ""
        payload = item.get("action_payload")
        fields = {
            "name": str(item.get("name") or ""),
            "position": item["position"],
            "type": str(item.get("type") or ""),
            "schema": str(schema),
            "has_offers": bool(offers) or schema == "landings",
            "filters": item.get("filters") or [],
            "action_payload": payload if isinstance(payload, str) else None,
        }
        stream = existing.get(item["id"])
        if stream is None:
            stream = Stream(campaign_id=campaign.id, kt_id=item["id"], **fields)
            session.add(stream)
            await session.flush()
        else:
            for k, v in fields.items():
                setattr(stream, k, v)

        rows = {
            r.kt_offer_id: r
            for r in await session.scalars(
                select(StreamOffer).where(StreamOffer.stream_id == stream.id)
            )
        }
        in_kt = {
            o["offer_id"]: o["share"] for o in offers if o.get("state") == "active"
        }
        for oid, row in rows.items():
            row.synced_active = oid in in_kt
            row.synced_share = in_kt.get(oid, 0)
            if oid in in_kt:
                row.seen_in_kt = True
        position = max((r.position for r in rows.values()), default=0)
        for oid, share in in_kt.items():
            if oid not in rows:
                position += 1
                rows[oid] = StreamOffer(
                    stream_id=stream.id,
                    kt_offer_id=oid,
                    name=names.get(oid, f"#{oid}"),
                    position=position,
                    synced_active=True,
                    synced_share=share,
                    active=True,
                    share=share,
                    seen_in_kt=True,
                )
                session.add(rows[oid])
        for row in rows.values():
            row.active = row.synced_active
            row.share = row.synced_share
            if not row.active:
                row.pinned = False

    campaign.synced_at = datetime.now(UTC)
    campaign.kt_deleted = False
    await session.commit()


async def sync_campaigns(session: AsyncSession, kt: KeitaroClient) -> None:
    ids = list(await session.scalars(select(Campaign.id)))
    for cid in ids:
        campaign = await session.get(Campaign, cid)
        if campaign is None:
            continue
        kt_id = campaign.kt_id
        try:
            await sync_campaign(session, kt, campaign)
        except KeitaroError as e:
            await session.rollback()
            log.warning(
                "Campaign sync skipped for kt_id=%s: status=%s: %s",
                kt_id,
                e.status,
                e.body[:200],
            )


async def _sync_campaigns_safe() -> None:
    try:
        async with db.async_session() as session:
            await sync_campaigns(session, get_kt())
    except Exception as e:
        log.warning("Campaign sync failed: %s: %s", type(e).__name__, str(e)[:200])


async def sync_after_login() -> None:
    await sync_offers_safe()
    await _sync_campaigns_safe()
