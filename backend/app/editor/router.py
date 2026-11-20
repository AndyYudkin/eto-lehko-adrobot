import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.sync import sync_campaign
from app.creator.router import _with_counts
from app.db import get_session
from app.editor import drafts
from app.editor.schemas import CampaignStreamsOut, StreamOut
from app.editor.views import stream_view
from app.keitaro.client import KeitaroClient, get_kt
from app.models import Campaign, Stream, StreamOffer
from app.offers.sync import sync_offers

router = APIRouter()


async def _streams_out(session: AsyncSession, campaign: Campaign) -> CampaignStreamsOut:
    streams = list(
        await session.scalars(
            select(Stream)
            .where(Stream.campaign_id == campaign.id)
            .order_by(Stream.has_offers.desc(), Stream.position)
        )
    )
    offers = list(
        await session.scalars(
            select(StreamOffer)
            .where(StreamOffer.stream_id.in_([s.id for s in streams]))
            .execution_options(populate_existing=True)
        )
    )
    return CampaignStreamsOut(
        campaign=(await _with_counts(session, [campaign]))[0],
        streams=[
            stream_view(s, [o for o in offers if o.stream_id == s.id]) for s in streams
        ],
    )


async def _campaign_or_404(session: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None or campaign.kt_deleted:
        raise HTTPException(404, "Campaign not found")
    return campaign


@router.get("/campaigns/{campaign_id}/streams", response_model=CampaignStreamsOut)
async def campaign_streams(
    campaign_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> CampaignStreamsOut:
    return await _streams_out(session, await _campaign_or_404(session, campaign_id))


@router.post("/campaigns/{campaign_id}/fetch", response_model=CampaignStreamsOut)
async def fetch_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    kt: KeitaroClient = Depends(get_kt),
) -> CampaignStreamsOut:
    campaign = await _campaign_or_404(session, campaign_id)
    await sync_offers(session, kt)
    await sync_campaign(session, kt, campaign)
    if campaign.kt_deleted:
        raise HTTPException(410, "Campaign was deleted in Keitaro")
    return await _streams_out(session, campaign)


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignStreamsOut)
async def cancel_campaign(
    campaign_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> CampaignStreamsOut:
    campaign = await _campaign_or_404(session, campaign_id)
    await drafts.cancel(session, campaign)
    return await _streams_out(session, campaign)


@router.post("/campaigns/{campaign_id}/push", response_model=CampaignStreamsOut)
async def push_campaign(
    campaign_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    kt: KeitaroClient = Depends(get_kt),
) -> CampaignStreamsOut:
    campaign = await _campaign_or_404(session, campaign_id)
    await drafts.push(session, kt, campaign)
    if campaign.kt_deleted:
        raise HTTPException(410, "Campaign was deleted in Keitaro")
    return await _streams_out(session, campaign)


class AddOfferIn(BaseModel):
    offer_id: int


class PinIn(BaseModel):
    pinned: bool


@router.post("/streams/{stream_id}/offers", response_model=StreamOut)
async def add_offer(
    stream_id: uuid.UUID,
    data: AddOfferIn,
    session: AsyncSession = Depends(get_session),
) -> StreamOut:
    stream = await drafts.add_offer(session, stream_id, data.offer_id)
    return await drafts.view(session, stream)


@router.delete("/streams/{stream_id}/offers/{offer_id}", response_model=StreamOut)
async def remove_offer(
    stream_id: uuid.UUID,
    offer_id: int,
    session: AsyncSession = Depends(get_session),
) -> StreamOut:
    stream = await drafts.remove_offer(session, stream_id, offer_id)
    return await drafts.view(session, stream)


@router.patch("/streams/{stream_id}/offers/{offer_id}", response_model=StreamOut)
async def pin_offer(
    stream_id: uuid.UUID,
    offer_id: int,
    data: PinIn,
    session: AsyncSession = Depends(get_session),
) -> StreamOut:
    stream = await drafts.set_pinned(session, stream_id, offer_id, data.pinned)
    return await drafts.view(session, stream)
