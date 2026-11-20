import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class Offer(Base):
    __tablename__ = "offers"

    kt_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kt_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String)
    alias: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    geo: Mapped[list[str]] = mapped_column(ARRAY(String))
    offer_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    kt_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    kt_id: Mapped[int] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column()
    type: Mapped[str] = mapped_column(String)
    schema: Mapped[str] = mapped_column(String)
    has_offers: Mapped[bool] = mapped_column(Boolean)
    filters: Mapped[list] = mapped_column(JSON)
    action_payload: Mapped[str | None] = mapped_column(String, default=None)


class StreamOffer(Base):
    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "kt_offer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    stream_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("streams.id", ondelete="CASCADE")
    )
    kt_offer_id: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column()
    synced_active: Mapped[bool] = mapped_column(Boolean)
    synced_share: Mapped[int] = mapped_column()
    active: Mapped[bool] = mapped_column(Boolean)
    share: Mapped[int] = mapped_column()
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # was this offer ever in the Keitaro stream? An offer added here and never
    # pushed has no history, so Remove / Cancel drop the row instead of
    # keeping a grey "removed" one.
    seen_in_kt: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
