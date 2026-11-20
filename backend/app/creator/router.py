from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.creator import service
from app.creator.schemas import CampaignOut, CreateCampaignIn
from app.db import get_session
from app.keitaro.client import KeitaroClient, get_kt
from app.models import Campaign, Stream, StreamOffer

router = APIRouter(prefix="/campaigns")


async def _with_counts(
    session: AsyncSession, campaigns: list[Campaign]
) -> list[CampaignOut]:
    rows = await session.execute(
        select(Stream.campaign_id, func.count(StreamOffer.id))
        .join(StreamOffer, StreamOffer.stream_id == Stream.id)
        .where(Stream.has_offers, StreamOffer.active)
        .group_by(Stream.campaign_id)
    )
    counts = dict(rows.all())
    return [
        CampaignOut.model_validate(c).model_copy(
            update={"offers_count": counts.get(c.id, 0)}
        )
        for c in campaigns
    ]


@router.post("", status_code=201, response_model=CampaignOut)
async def create_campaign(
    data: CreateCampaignIn,
    session: AsyncSession = Depends(get_session),
    kt: KeitaroClient = Depends(get_kt),
    settings: Settings = Depends(get_settings),
) -> CampaignOut:
    c = await service.create_campaign(session, kt, settings, data)
    return (await _with_counts(session, [c]))[0]


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    session: AsyncSession = Depends(get_session),
) -> list[CampaignOut]:
    result = await session.scalars(
        select(Campaign)
        .where(Campaign.kt_deleted.is_(False))  # gone from Keitaro: hide
        .order_by(Campaign.created_at.desc())
    )
    return await _with_counts(session, list(result))
