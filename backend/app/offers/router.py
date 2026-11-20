import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Offer, Stream, StreamOffer

router = APIRouter(prefix="/offers")


class OfferOut(BaseModel):
    id: int
    name: str


@router.get("", response_model=list[OfferOut])
async def search_offers(
    q: str = "",
    exclude_stream: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[OfferOut]:
    """`exclude_stream`: leave out offers already in that stream — active ones
    and removed ones alike (those come back via Bring back, not via search)."""
    q = q.strip()
    if not q:
        return []
    if exclude_stream is not None and await session.get(Stream, exclude_stream) is None:
        raise HTTPException(404, "Stream not found")
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cond = Offer.name.ilike(f"%{escaped}%", escape="\\")
    if q.isascii() and q.isdigit() and len(q) <= 18:
        cond = or_(cond, Offer.kt_id == int(q))
    rows = await session.scalars(
        select(Offer)
        .where(Offer.state == "active", cond)
        .where(
            Offer.kt_id.not_in(
                select(StreamOffer.kt_offer_id).where(
                    StreamOffer.stream_id == exclude_stream
                )
            )
            if exclude_stream is not None
            else True
        )
        .order_by(Offer.name)
    )
    return [OfferOut(id=o.kt_id, name=o.name) for o in rows]
