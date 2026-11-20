import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.sync import parse_streams, sync_campaign
from app.editor.schemas import StreamOut
from app.editor.views import is_dirty, stream_view
from app.keitaro.client import KeitaroClient
from app.keitaro.payloads import offers_update_payload
from app.models import Campaign, Offer, Stream, StreamOffer
from app.shares import ShareItem, push_block_reason, recalc_shares

STREAM_CHANGED_IN_KT = (
    "A stream was changed in Keitaro. Press Cancel, then Fetch from KT"
)


async def _offers(session: AsyncSession, stream: Stream) -> list[StreamOffer]:
    result = await session.scalars(
        select(StreamOffer)
        .where(StreamOffer.stream_id == stream.id)
        .order_by(StreamOffer.position)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def view(session: AsyncSession, stream: Stream) -> StreamOut:
    return stream_view(stream, await _offers(session, stream))


async def get_stream(session: AsyncSession, stream_id: uuid.UUID) -> Stream:
    stream = await session.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(404, "Stream not found")
    return stream


async def _row(session: AsyncSession, stream: Stream, offer_id: int) -> StreamOffer:
    row = await session.scalar(
        select(StreamOffer).where(
            StreamOffer.stream_id == stream.id,
            StreamOffer.kt_offer_id == offer_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Offer not in stream")
    return row


def _recalc(offers: list[StreamOffer]) -> None:
    active = [o for o in offers if o.active]
    new = recalc_shares(
        [ShareItem(o.kt_offer_id, o.share, o.pinned, o.position) for o in active]
    )
    for o in active:
        o.share = new[o.kt_offer_id]


async def add_offer(
    session: AsyncSession, stream_id: uuid.UUID, offer_id: int
) -> Stream:
    stream = await get_stream(session, stream_id)
    if not stream.has_offers:
        raise HTTPException(409, "Stream has no offers")
    offers = await _offers(session, stream)
    existing = next((o for o in offers if o.kt_offer_id == offer_id), None)
    if existing is not None:
        if existing.active:
            raise HTTPException(409, "Offer is already in the stream")
        existing.active, existing.pinned = True, False
    else:
        catalog = await session.get(Offer, offer_id)
        if catalog is None or catalog.state != "active":
            raise HTTPException(404, "Offer not found")
        existing = StreamOffer(
            stream_id=stream.id,
            kt_offer_id=offer_id,
            name=catalog.name,
            position=max((o.position for o in offers), default=0) + 1,
            synced_active=False,
            synced_share=0,
            active=True,
            share=0,
            pinned=False,
            seen_in_kt=False,
        )
        session.add(existing)
        offers.append(existing)
    _recalc(offers)
    await session.commit()
    return stream


async def remove_offer(
    session: AsyncSession, stream_id: uuid.UUID, offer_id: int
) -> Stream:
    stream = await get_stream(session, stream_id)
    row = await _row(session, stream, offer_id)
    if row.seen_in_kt:
        row.active, row.share, row.pinned = False, 0, False
    else:
        await session.delete(row)  # never in Keitaro: nothing to keep
        await session.flush()
    _recalc(await _offers(session, stream))
    await session.commit()
    return stream


async def set_pinned(
    session: AsyncSession, stream_id: uuid.UUID, offer_id: int, pinned: bool
) -> Stream:
    stream = await get_stream(session, stream_id)
    row = await _row(session, stream, offer_id)
    if not row.active:
        raise HTTPException(409, "Offer is removed")
    row.pinned = pinned
    if not pinned:
        # unpinned share goes back to the pool; pinning just freezes the
        # current value, so the sum is still 100 and nothing to recalc
        _recalc(await _offers(session, stream))
    await session.commit()
    return stream


async def _campaign_streams(session: AsyncSession, campaign: Campaign) -> list[Stream]:
    result = await session.scalars(
        select(Stream).where(Stream.campaign_id == campaign.id)
    )
    return list(result)


async def cancel(session: AsyncSession, campaign: Campaign) -> None:
    """Drop the whole campaign draft: every stream back to what Keitaro has."""
    for stream in await _campaign_streams(session, campaign):
        for o in await _offers(session, stream):
            if not o.seen_in_kt:
                await session.delete(o)  # added here, never pushed
                continue
            o.active, o.share = o.synced_active, o.synced_share
            if not o.active:
                o.pinned = False
    await session.commit()


async def _check_unchanged_in_kt(
    kt: KeitaroClient,
    campaign: Campaign,
    pending: list[tuple[Stream, list[StreamOffer], list[StreamOffer]]],
) -> None:
    """Push replaces a stream's offers, so refuse if Keitaro no longer has
    what we last synced: someone changed it there and Push would wipe it."""
    in_kt = {
        item["id"]: {
            o["offer_id"]: o["share"]
            for o in item["offers"]
            if o.get("state") == "active"
        }
        for item in parse_streams(await kt.get_campaign_streams(campaign.kt_id))
    }
    for stream, offers, _ in pending:
        synced = {o.kt_offer_id: o.synced_share for o in offers if o.synced_active}
        if in_kt.get(stream.kt_id) != synced:
            raise HTTPException(409, STREAM_CHANGED_IN_KT)


async def push(session: AsyncSession, kt: KeitaroClient, campaign: Campaign) -> None:
    """Send every changed stream to Keitaro; nothing is sent if any of them
    can't be pushed."""
    pending: list[tuple[Stream, list[StreamOffer]]] = []
    for stream in await _campaign_streams(session, campaign):
        offers = await _offers(session, stream)
        if not stream.has_offers or not is_dirty(offers):
            continue
        active = [o for o in offers if o.active]
        reason = push_block_reason([o.share for o in active])
        if reason is not None:
            raise HTTPException(409, reason)
        pending.append((stream, offers, active))
    if pending:
        await _check_unchanged_in_kt(kt, campaign, pending)
    for stream, _, active in pending:
        await kt.update_stream(
            stream.kt_id,
            offers_update_payload([(o.kt_offer_id, o.share) for o in active]),
        )
    # re-read from Keitaro so synced state is what it really has now
    await sync_campaign(session, kt, campaign)
