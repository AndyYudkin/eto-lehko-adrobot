import logging
from datetime import UTC, datetime

import pytest
import respx
from sqlalchemy import select

from app.auth.service import seed_user
from app.campaigns.sync import sync_campaign, sync_campaigns
from app.config import get_settings
from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import Campaign, Offer, Stream, StreamOffer

KT = "http://kt.test"
API = f"{KT}/admin_api/v1"


@pytest.fixture
def kt_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "kt_url", KT)
    monkeypatch.setattr(s, "kt_api_key", "test-key")


def _kt():
    return KeitaroClient(KT, "test-key")


async def _campaign(session, kt_id=77):
    c = Campaign(kt_id=kt_id, name="c", alias="a", url="u", geo=["MX"], offer_id=1)
    session.add(c)
    await session.commit()
    return c


def _stream(sid, position, offers, schema="redirect", **kw):
    return {
        "id": sid,
        "type": "regular",
        "name": f"S{sid}",
        "position": position,
        "state": "active",
        "schema": schema,
        "action_type": "http",
        "action_payload": "https://google.com",
        "filters": [{"name": "country", "mode": "accept", "payload": ["MX"]}],
        "offers": [
            {"id": 1000 + o, "offer_id": o, "share": sh, "state": st}
            for o, sh, st in offers
        ],
        **kw,
    }


def _mock_campaign(kt_id=77):
    return respx.get(f"{API}/campaigns/{kt_id}").respond(json={"id": kt_id})


def _mock_streams(items, kt_id=77):
    _mock_campaign(kt_id)
    return respx.get(f"{API}/campaigns/{kt_id}/streams").respond(json=items)


STREAMS = [
    _stream(1, 1, [], schema="redirect"),
    _stream(2, 2, [(10, 34, "active"), (11, 33, "active"), (12, 33, "active")]),
]


async def _offer_rows(session):
    session.expire_all()
    rows = await session.scalars(select(StreamOffer).order_by(StreamOffer.kt_offer_id))
    return {
        r.kt_offer_id: (r.active, r.share, r.synced_active, r.synced_share, r.pinned)
        for r in rows
    }


async def _pin(session, offer_id, share):
    r = await session.scalar(
        select(StreamOffer).where(StreamOffer.kt_offer_id == offer_id)
    )
    r.share, r.pinned = share, True
    await session.commit()


@respx.mock
async def test_initial_fetch(session):
    session.add(
        Offer(kt_id=10, name="Alpha", state="active", synced_at=datetime.now(UTC))
    )
    c = await _campaign(session)
    cid = c.id
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    session.expire_all()
    streams = list(await session.scalars(select(Stream).order_by(Stream.position)))
    assert [(s.kt_id, s.has_offers) for s in streams] == [(1, False), (2, True)]
    assert streams[0].action_payload == "https://google.com"
    assert streams[0].filters[0]["name"] == "country"
    assert await _offer_rows(session) == {
        10: (True, 34, True, 34, False),
        11: (True, 33, True, 33, False),
        12: (True, 33, True, 33, False),
    }
    names = {r.kt_offer_id: r.name for r in await session.scalars(select(StreamOffer))}
    assert names == {10: "Alpha", 11: "#11", 12: "#12"}
    c = await session.get(Campaign, cid)
    assert c.synced_at is not None and c.kt_deleted is False


@respx.mock
async def test_offer_removed_in_kt(session):
    c = await _campaign(session)
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    await _pin(session, 11, 50)
    respx.clear()
    _mock_streams([STREAMS[0], _stream(2, 2, [(10, 50, "active"), (12, 50, "active")])])
    await sync_campaign(session, _kt(), c)
    rows = await _offer_rows(session)
    assert rows[11] == (False, 0, False, 0, False)
    assert rows[10] == (True, 50, True, 50, False)


@respx.mock
async def test_offer_added_in_kt(session):
    c = await _campaign(session)
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    respx.clear()
    _mock_streams(
        [
            STREAMS[0],
            _stream(
                2,
                2,
                [
                    (10, 25, "active"),
                    (11, 25, "active"),
                    (12, 25, "active"),
                    (13, 25, "active"),
                ],
            ),
        ]
    )
    await sync_campaign(session, _kt(), c)
    rows = await _offer_rows(session)
    assert rows[13] == (True, 25, True, 25, False)
    positions = {
        r.kt_offer_id: r.position for r in await session.scalars(select(StreamOffer))
    }
    assert positions[13] == 4


@respx.mock
async def test_fetch_discards_draft_keeps_pins(session):
    c = await _campaign(session)
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    await _pin(session, 10, 60)
    await sync_campaign(session, _kt(), c)
    rows = await _offer_rows(session)
    assert rows[10] == (True, 34, True, 34, True)


@respx.mock
async def test_kt_sum_not_100_imported_as_is(session):
    c = await _campaign(session)
    _mock_streams([_stream(2, 2, [(10, 50, "active"), (11, 30, "active")])])
    await sync_campaign(session, _kt(), c)
    rows = await _offer_rows(session)
    assert rows[10][:2] == (True, 50) and rows[11][:2] == (True, 30)


@respx.mock
async def test_campaign_gone(session):
    c = await _campaign(session)
    cid = c.id
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    before = await _offer_rows(session)
    respx.clear()
    c = await session.get(Campaign, cid)
    # archived in Keitaro: the campaign 404s (nginx page), streams still answer
    respx.get(f"{API}/campaigns/77").respond(404, text="<html>404 Not Found</html>")
    streams = respx.get(f"{API}/campaigns/77/streams").respond(json=STREAMS[:1])
    await sync_campaign(session, _kt(), c)
    session.expire_all()
    assert (await session.get(Campaign, cid)).kt_deleted is True
    assert not streams.called
    assert await _offer_rows(session) == before
    assert len(list(await session.scalars(select(Stream)))) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "nope"},
        [{"id": "x", "position": 1, "offers": []}],
        [{"id": 1, "position": 1, "offers": None}],
        [{"id": 1, "position": 1, "offers": [{"offer_id": "5", "share": 1}]}],
        [{"id": 1, "position": 1, "offers": [{"offer_id": 5, "share": None}]}],
    ],
)
@respx.mock
async def test_bad_streams_payload_keeps_data(session, payload):
    c = await _campaign(session)
    cid = c.id
    _mock_streams(STREAMS)
    await sync_campaign(session, _kt(), c)
    before = await _offer_rows(session)
    respx.clear()
    c = await session.get(Campaign, cid)
    _mock_streams(payload)
    with pytest.raises(KeitaroError):
        await sync_campaign(session, _kt(), c)
    assert await _offer_rows(session) == before
    assert len(list(await session.scalars(select(Stream)))) == 2


@respx.mock
async def test_sync_campaigns_continues_after_failure(session, caplog):
    await _campaign(session, 77)
    await _campaign(session, 78)
    _mock_streams(STREAMS, 77)
    _mock_campaign(78)
    respx.get(f"{API}/campaigns/78/streams").respond(500)
    with caplog.at_level(logging.WARNING):
        await sync_campaigns(session, _kt())
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "78" in warnings[0].getMessage()
    assert len(list(await session.scalars(select(Stream)))) == 2


@respx.mock
async def test_login_syncs_offers_then_campaigns(client, session, kt_configured):
    await seed_user(session, "admin", "test-password")
    await _campaign(session)
    offers = respx.get(f"{API}/offers").respond(
        json=[{"id": 10, "name": "Alpha", "state": "active"}]
    )
    streams = _mock_streams(STREAMS)
    r = await client.post(
        "/api/auth/login", json={"login": "admin", "password": "test-password"}
    )
    assert r.status_code == 204
    assert offers.calls.call_count == 1 and streams.calls.call_count == 1
    order = [c.request.url.path for c in respx.calls]
    assert order == [
        "/admin_api/v1/offers",
        "/admin_api/v1/campaigns/77",
        "/admin_api/v1/campaigns/77/streams",
    ]
    session.expire_all()
    assert (await _offer_rows(session))[10][1] == 34
    name = await session.scalar(
        select(StreamOffer.name).where(StreamOffer.kt_offer_id == 10)
    )
    assert name == "Alpha"


@respx.mock
async def test_list_offers_count(auth_client, session, kt_configured):
    c = await _campaign(session)
    _mock_streams(
        [
            _stream(1, 1, [], schema="redirect"),
            _stream(2, 2, [(10, 50, "active"), (11, 50, "active")]),
        ]
    )
    await sync_campaign(session, _kt(), c)
    await _pin(session, 11, 50)
    row = await session.scalar(select(StreamOffer).where(StreamOffer.kt_offer_id == 11))
    row.active = False
    await session.commit()
    body = (await auth_client.get("/api/campaigns")).json()
    assert body[0]["offers_count"] == 1
    assert body[0]["kt_deleted"] is False
