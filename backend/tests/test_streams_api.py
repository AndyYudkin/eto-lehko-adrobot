import uuid
from datetime import UTC, datetime

import respx

from app.models import Campaign, Stream, StreamOffer


async def _campaign(session, kt_id=1, **kw) -> Campaign:
    c = Campaign(
        kt_id=kt_id,
        name="C",
        alias="a",
        url="http://x",
        geo=["US"],
        offer_id=1,
        **kw,
    )
    session.add(c)
    await session.flush()
    return c


def _stream(c, kt_id, position, has_offers=True, **kw) -> Stream:
    return Stream(
        campaign_id=c.id,
        kt_id=kt_id,
        name=f"S{kt_id}",
        position=position,
        type="regular",
        schema="landings" if not has_offers else "offers",
        has_offers=has_offers,
        filters=kw.pop("filters", []),
        **kw,
    )


def _so(
    stream,
    offer_id,
    position,
    share,
    active=True,
    synced=None,
    pinned=False,
    seen_in_kt=True,
):
    sa, ss = synced if synced is not None else (active, share)
    return StreamOffer(
        stream_id=stream.id,
        kt_offer_id=offer_id,
        name=f"O{offer_id}",
        position=position,
        synced_active=sa,
        synced_share=ss,
        active=active,
        share=share,
        pinned=pinned,
        seen_in_kt=seen_in_kt,
    )


async def _seed_stream(session, c, offers, kt_id=10, position=1):
    s = _stream(c, kt_id, position)
    session.add(s)
    await session.flush()
    session.add_all(_so(s, *o[:4], **o[4]) for o in offers)
    await session.commit()
    return s


async def test_shape_and_ordering(auth_client, session):
    c = await _campaign(session, synced_at=datetime.now(UTC))
    geo = _stream(
        c,
        20,
        1,
        has_offers=False,
        filters=[{"name": "country", "mode": "accept", "payload": ["US"], "id": 5}],
        action_payload="https://google.com",
    )
    session.add(geo)
    await session.flush()
    await _seed_stream(
        session,
        c,
        [
            (1, 0, 10, True, {}),
            (2, 1, 60, True, {}),
            (3, 2, 30, True, {}),
            (4, 3, 0, False, {"synced": (True, 10)}),
        ],
        kt_id=10,
        position=2,
    )
    r = await auth_client.get(f"/api/campaigns/{c.id}/streams")
    assert r.status_code == 200
    body = r.json()
    assert body["campaign"]["id"] == str(c.id)
    assert body["campaign"]["synced_at"] is not None
    assert [s["kt_id"] for s in body["streams"]] == [10, 20]
    offers, redirect = body["streams"]
    assert [o["offer_id"] for o in offers["offers"]] == [2, 3, 1, 4]
    assert set(offers["offers"][0]) == {
        "offer_id",
        "name",
        "share",
        "pinned",
        "active",
    }
    assert offers["has_offers"] is True
    assert redirect["has_offers"] is False
    assert redirect["offers"] == []
    assert redirect["push_block_reason"] is None
    assert redirect["action_payload"] == "https://google.com"
    assert redirect["filters"] == [
        {"name": "country", "mode": "accept", "payload": ["US"]}
    ]
    assert {"id", "kt_id", "name", "position", "type", "schema", "dirty"} <= set(
        redirect
    )


async def test_added_offer_makes_dirty(auth_client, session):
    c = await _campaign(session)
    await _seed_stream(
        session,
        c,
        [
            (1, 0, 50, True, {}),
            (2, 1, 50, True, {"synced": (False, 0)}),
        ],
    )
    s = (await auth_client.get(f"/api/campaigns/{c.id}/streams")).json()["streams"][0]
    assert s["dirty"] is True


async def test_clean_not_dirty(auth_client, session):
    c = await _campaign(session)
    await _seed_stream(session, c, [(1, 0, 100, True, {})])
    s = (await auth_client.get(f"/api/campaigns/{c.id}/streams")).json()["streams"][0]
    assert s["dirty"] is False
    assert s["push_block_reason"] is None


async def test_push_block_reasons(auth_client, session):
    c = await _campaign(session)
    await _seed_stream(session, c, [(1, 0, 0, False, {"synced": (True, 100)})])
    await _seed_stream(session, c, [(2, 0, 40, True, {})], kt_id=11, position=2)
    got = {
        s["kt_id"]: s["push_block_reason"]
        for s in (await auth_client.get(f"/api/campaigns/{c.id}/streams")).json()[
            "streams"
        ]
    }
    assert got == {10: "no_offers", 11: "sum_not_100"}


async def test_unknown_campaign_404(auth_client):
    r = await auth_client.get(f"/api/campaigns/{uuid.uuid4()}/streams")
    assert r.status_code == 404


async def test_kt_deleted_404(auth_client, session):
    c = await _campaign(session, kt_deleted=True)
    await session.commit()
    r = await auth_client.get(f"/api/campaigns/{c.id}/streams")
    assert r.status_code == 404


async def test_requires_auth(client):
    r = await client.get(f"/api/campaigns/{uuid.uuid4()}/streams")
    assert r.status_code == 401


@respx.mock
async def test_no_keitaro_call(auth_client, session):
    c = await _campaign(session)
    await session.commit()
    r = await auth_client.get(f"/api/campaigns/{c.id}/streams")
    assert r.status_code == 200
    assert len(respx.calls) == 0
