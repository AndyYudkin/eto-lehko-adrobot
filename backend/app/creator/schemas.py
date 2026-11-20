import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

GEO_RE = re.compile(r"^[A-Z]{2}$")


class CreateCampaignIn(BaseModel):
    name: str
    geo: list[str]
    offer_id: int

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("geo")
    @classmethod
    def _geo(cls, v: list[str]) -> list[str]:
        codes = list(dict.fromkeys(g.strip().upper() for g in v))
        if not codes:
            raise ValueError("geo must not be empty")
        for c in codes:
            if not GEO_RE.match(c):
                raise ValueError(f"invalid geo code: {c!r}")
        return codes


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kt_id: int
    name: str
    url: str
    geo: list[str]
    offer_id: int
    created_at: datetime
    kt_deleted: bool = False
    offers_count: int = 0
    synced_at: datetime | None = None
