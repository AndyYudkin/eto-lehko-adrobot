import logging
import secrets
import string

from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.sync import sync_campaign
from app.config import Settings
from app.creator.refs import ConfigError, campaign_url, resolve_refs
from app.creator.schemas import CreateCampaignIn
from app.keitaro.client import KeitaroClient
from app.keitaro.payloads import (
    campaign_payload,
    geo_stream_payload,
    offer_stream_payload,
)
from app.models import Campaign, Offer

log = logging.getLogger(__name__)

ALIAS_CHARS = string.ascii_letters + string.digits
ALIAS_LEN = 7


async def create_campaign(
    session: AsyncSession,
    kt: KeitaroClient,
    settings: Settings,
    data: CreateCampaignIn,
) -> Campaign:
    offer = await session.get(Offer, data.offer_id)
    if offer is None or offer.state != "active":
        raise ConfigError(f"Оффер #{data.offer_id} не найден или не активен")

    refs = await resolve_refs(kt, settings)

    prefix = settings.campaign_name_prefix
    name = data.name if data.name.startswith(prefix) else prefix + data.name

    alias = "".join(secrets.choice(ALIAS_CHARS) for _ in range(ALIAS_LEN))
    created = await kt.create_campaign(
        campaign_payload(
            name,
            alias,
            refs.domain_id,
            refs.group_id,
            refs.traffic_source_id,
        )
    )
    kt_id = created["id"]

    try:
        await kt.create_stream(geo_stream_payload(kt_id, data.geo))
        await kt.create_stream(offer_stream_payload(kt_id, data.offer_id))
    except Exception:
        try:
            await kt.delete_campaign(kt_id)
        except Exception:
            log.warning("Failed to roll back Keitaro campaign %s", kt_id, exc_info=True)
        raise

    real_alias = created.get("alias")
    if not isinstance(real_alias, str) or not real_alias:
        real_alias = alias
    campaign = Campaign(
        kt_id=kt_id,
        name=name,
        alias=real_alias,
        url=campaign_url(refs, real_alias),
        geo=data.geo,
        offer_id=data.offer_id,
    )
    session.add(campaign)
    await session.commit()
    try:
        await sync_campaign(session, kt, campaign)
    except Exception as e:  # the campaign exists in Keitaro; 201 regardless
        await session.rollback()
        log.warning(
            "Stream sync after create failed for kt_id=%s: %s: %s",
            kt_id,
            type(e).__name__,
            str(e)[:200],
        )
    await session.refresh(campaign)
    return campaign
