import uuid

from pydantic import BaseModel, Field

from app.creator.schemas import CampaignOut


class FilterOut(BaseModel):
    name: str
    mode: str
    payload: object = None


class OfferOut(BaseModel):
    offer_id: int
    name: str
    share: int
    pinned: bool
    active: bool


class StreamOut(BaseModel):
    id: uuid.UUID
    kt_id: int
    name: str
    position: int
    type: str
    schema_: str = Field(serialization_alias="schema")
    has_offers: bool
    filters: list[FilterOut]
    action_payload: str | None
    dirty: bool
    push_block_reason: str | None
    offers: list[OfferOut]


class CampaignStreamsOut(BaseModel):
    campaign: CampaignOut
    streams: list[StreamOut]
