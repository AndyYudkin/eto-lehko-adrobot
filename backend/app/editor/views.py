from app.editor.schemas import FilterOut, OfferOut, StreamOut
from app.models import Stream, StreamOffer
from app.shares import push_block_reason


def is_dirty(offers: list[StreamOffer]) -> bool:
    """Draft differs from what Keitaro has."""
    return any((o.active, o.share) != (o.synced_active, o.synced_share) for o in offers)


def stream_view(stream: Stream, offers: list[StreamOffer]) -> StreamOut:
    ordered = sorted(
        offers, key=lambda o: (not o.active, -o.share if o.active else 0, o.position)
    )
    return StreamOut(
        id=stream.id,
        kt_id=stream.kt_id,
        name=stream.name,
        position=stream.position,
        type=stream.type,
        schema_=stream.schema,
        has_offers=stream.has_offers,
        filters=[
            FilterOut(
                name=f.get("name", ""),
                mode=f.get("mode", ""),
                payload=f.get("payload"),
            )
            for f in stream.filters
        ],
        action_payload=stream.action_payload,
        dirty=is_dirty(offers),
        push_block_reason=(
            push_block_reason([o.share for o in offers if o.active])
            if stream.has_offers
            else None
        ),
        offers=[
            OfferOut(
                offer_id=o.kt_offer_id,
                name=o.name,
                share=o.share,
                pinned=o.pinned,
                active=o.active,
            )
            for o in ordered
        ],
    )
