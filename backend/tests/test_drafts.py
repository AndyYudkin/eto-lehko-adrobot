import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import select

from app.config import get_settings
from app.models import Offer, StreamOffer
from tests.test_streams_api import _campaign, _seed_stream

KT = "http://kt.test"
API = f"{KT}/admin_api/v1"
STREAM_KT_ID = 10


@pytest.fixture(autouse=True)
def _kt_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "kt_url", KT)
    monkeypatch.setattr(s, "kt_api_key", "test-key")


async def _setup(session, kt_id=77, **kw):
    """Campaign with one offer stream A,B,C = 34/33/33, plus catalog offers."""
    c = await _campaign(session, kt_id=kt_id, **kw)
    s = await _seed_stream(
        session,
        c,
        [(1, 0, 34, True, {}), (2, 1, 33, True, {}), (3, 2, 33, True, {})],
        kt_id=STREAM_KT_ID,
    )
    now = datetime.now(UTC)
    session.add_all(
        [
            Offer(kt_id=4, name="D", state="active", synced_at=now),
            Offer(kt_id=5, name="Off", state="disabled", synced_at=now),
        ]
    )
    await session.commit()
    return c, s


def _shares(body):
    return {o["offer_id"]: o["share"] for o in body["offers"]}


async def _add(client, s, offer_id):
    return await client.post(f"/api/streams/{s.id}/offers", json={"offer_id": offer_id})


def _kt_stream(kt_id, offers, position=1):
    """A Keitaro stream with (offer_id, share) active offers."""
    return {
        "id": kt_id,
        "position": position,
        "schema": "landings",
        "offers": [
            {"offer_id": oid, "share": share, "state": "active"}
            for oid, share in offers
        ],
    }


# what Keitaro has for _setup's stream: A,B,C = 34/33/33
KT_BEFORE = _kt_stream(STREAM_KT_ID, [(1, 34), (2, 33), (3, 33)])


async def test_add_recalcs(auth_client, session):
    _, s = await _setup(session)
    r = await _add(auth_client, s, 4)
    assert r.status_code == 200
    body = r.json()
    assert _shares(body) == {1: 25, 2: 25, 3: 25, 4: 25}
    assert body["dirty"] is True
    d = next(o for o in body["offers"] if o["offer_id"] == 4)
    assert d["name"] == "D" and d["pinned"] is False


async def test_add_active_conflict(auth_client, session):
    _, s = await _setup(session)
    assert (await _add(auth_client, s, 1)).status_code == 409
    session.expire_all()
    rows = list(await session.scalars(select(StreamOffer)))
    assert len(rows) == 3


@pytest.mark.parametrize("offer_id", [4242, 5])
async def test_add_unknown_or_disabled_offer_404(auth_client, session, offer_id):
    _, s = await _setup(session)
    assert (await _add(auth_client, s, offer_id)).status_code == 404


async def test_add_unknown_stream_404(auth_client, session):
    await _setup(session)
    r = await auth_client.post(
        f"/api/streams/{uuid.uuid4()}/offers", json={"offer_id": 4}
    )
    assert r.status_code == 404


async def test_add_to_stream_without_offers_409(auth_client, session):
    c, _ = await _setup(session)
    from tests.test_streams_api import _stream

    g = _stream(c, 99, 5, has_offers=False)
    session.add(g)
    await session.commit()
    assert (await _add(auth_client, g, 4)).status_code == 409


async def test_pin_then_add(auth_client, session):
    _, s = await _setup(session)
    r = await auth_client.patch(f"/api/streams/{s.id}/offers/2", json={"pinned": True})
    assert r.status_code == 200
    assert r.json()["dirty"] is False  # pin alone is not a change
    r = await _add(auth_client, s, 4)
    assert _shares(r.json()) == {1: 23, 2: 33, 3: 22, 4: 22}


async def test_unpin_recalcs(auth_client, session):
    # B pinned at 33, D added → 23/33/22/22; unpinning B returns its share to
    # the pool, so all four are split evenly again
    _, s = await _setup(session)
    await auth_client.patch(f"/api/streams/{s.id}/offers/2", json={"pinned": True})
    await _add(auth_client, s, 4)
    r = await auth_client.patch(f"/api/streams/{s.id}/offers/2", json={"pinned": False})
    assert r.status_code == 200
    assert _shares(r.json()) == {1: 25, 2: 25, 3: 25, 4: 25}


async def test_remove_soft(auth_client, session):
    _, s = await _setup(session)
    r = await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    assert r.status_code == 200
    offers = r.json()["offers"]
    assert [o["offer_id"] for o in offers][-1] == 1
    a = offers[-1]
    assert a["active"] is False and a["share"] == 0 and a["pinned"] is False
    assert _shares(r.json()) == {1: 0, 2: 50, 3: 50}
    assert r.json()["dirty"] is True


async def test_remove_unknown_404(auth_client, session):
    _, s = await _setup(session)
    r = await auth_client.delete(f"/api/streams/{s.id}/offers/999")
    assert r.status_code == 404


async def test_bring_back(auth_client, session):
    _, s = await _setup(session)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    r = await _add(auth_client, s, 1)
    assert r.status_code == 200
    assert _shares(r.json()) == {1: 34, 2: 33, 3: 33}
    assert all(o["pinned"] is False for o in r.json()["offers"])
    assert r.json()["dirty"] is False


async def test_pin_inactive_409(auth_client, session):
    _, s = await _setup(session)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    r = await auth_client.patch(f"/api/streams/{s.id}/offers/1", json={"pinned": True})
    assert r.status_code == 409


async def test_pin_unknown_404(auth_client, session):
    _, s = await _setup(session)
    r = await auth_client.patch(
        f"/api/streams/{s.id}/offers/999", json={"pinned": True}
    )
    assert r.status_code == 404


@respx.mock
async def test_remove_pinned_leaves_all_pinned_blocks_push(auth_client, session):
    c, s = await _setup(session)
    for oid in (1, 2):
        await auth_client.patch(
            f"/api/streams/{s.id}/offers/{oid}", json={"pinned": True}
        )
    r = await auth_client.delete(f"/api/streams/{s.id}/offers/3")
    body = r.json()
    assert _shares(body) == {1: 34, 2: 33, 3: 0}
    assert body["push_block_reason"] == "sum_not_100"
    r = await auth_client.post(f"/api/campaigns/{c.id}/push")
    assert r.status_code == 409
    assert r.json() == {"detail": "sum_not_100"}
    assert len(respx.calls) == 0


async def test_remove_last(auth_client, session):
    _, s = await _setup(session)
    for oid in (1, 2, 3):
        r = await auth_client.delete(f"/api/streams/{s.id}/offers/{oid}")
    assert r.json()["push_block_reason"] == "no_offers"


async def test_cancel(auth_client, session):
    c, s = await _setup(session)
    await auth_client.patch(f"/api/streams/{s.id}/offers/2", json={"pinned": True})
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    await _add(auth_client, s, 4)
    r = await auth_client.post(f"/api/campaigns/{c.id}/cancel")
    assert r.status_code == 200
    body = r.json()["streams"][0]
    assert body["dirty"] is False
    # D was added here and never pushed: Cancel drops it entirely
    assert _shares(body) == {1: 34, 2: 33, 3: 33}
    assert [o["active"] for o in body["offers"]] == [True, True, True]
    assert next(o for o in body["offers"] if o["offer_id"] == 2)["pinned"] is True


@respx.mock
async def test_push(auth_client, session):
    c, s = await _setup(session)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    put = respx.put(f"{API}/streams/{STREAM_KT_ID}").respond(json={"id": 10})
    respx.get(f"{API}/campaigns/77").respond(json={"id": 77})
    respx.get(f"{API}/campaigns/77/streams").mock(
        side_effect=[
            httpx.Response(200, json=[KT_BEFORE]),
            httpx.Response(200, json=[_kt_stream(STREAM_KT_ID, [(2, 50), (3, 50)])]),
        ]
    )
    r = await auth_client.post(f"/api/campaigns/{c.id}/push")
    assert r.status_code == 200
    assert put.call_count == 1
    assert json.loads(put.calls[0].request.content) == {
        "offers": [
            {"offer_id": 2, "share": 50, "state": "active"},
            {"offer_id": 3, "share": 50, "state": "active"},
        ]
    }
    body = r.json()["streams"][0]
    assert body["dirty"] is False
    assert _shares(body) == {1: 0, 2: 50, 3: 50}
    a = next(o for o in body["offers"] if o["offer_id"] == 1)
    assert a["active"] is False
    session.expire_all()
    rows = {r.kt_offer_id: r for r in await session.scalars(select(StreamOffer))}
    assert rows[1].synced_active is False and rows[2].synced_share == 50


@respx.mock
async def test_push_keitaro_error_502_keeps_draft(auth_client, session):
    c, s = await _setup(session)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    respx.get(f"{API}/campaigns/77/streams").respond(json=[KT_BEFORE])
    respx.put(f"{API}/streams/{STREAM_KT_ID}").respond(500, text="boom")
    r = await auth_client.post(f"/api/campaigns/{c.id}/push")
    assert r.status_code == 502
    session.expire_all()
    rows = {r.kt_offer_id: r for r in await session.scalars(select(StreamOffer))}
    assert rows[1].active is False and rows[2].share == 50
    assert rows[1].synced_active is True and rows[2].synced_share == 33


def _mock_fetch(streams, campaign_status=200, kt_id=1):
    respx.get(f"{API}/offers").respond(json=[{"id": 4, "name": "D", "state": "active"}])
    respx.get(f"{API}/campaigns/{kt_id}").respond(campaign_status, json={"id": kt_id})
    respx.get(f"{API}/campaigns/{kt_id}/streams").respond(json=streams)


@respx.mock
async def test_fetch_resyncs_discards_draft_keeps_pins(auth_client, session):
    c, s = await _setup(session, kt_id=1)
    await auth_client.patch(f"/api/streams/{s.id}/offers/2", json={"pinned": True})
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    _mock_fetch(
        [
            {
                "id": STREAM_KT_ID,
                "position": 1,
                "schema": "landings",
                "offers": [
                    {"offer_id": 1, "share": 40, "state": "active"},
                    {"offer_id": 2, "share": 30, "state": "active"},
                    {"offer_id": 3, "share": 30, "state": "active"},
                ],
            }
        ]
    )
    r = await auth_client.post(f"/api/campaigns/{c.id}/fetch")
    assert r.status_code == 200
    body = r.json()
    assert body["campaign"]["id"] == str(c.id)
    st = body["streams"][0]
    assert st["dirty"] is False
    assert _shares(st) == {1: 40, 2: 30, 3: 30}
    assert next(o for o in st["offers"] if o["offer_id"] == 2)["pinned"] is True
    assert r.json() == (await auth_client.get(f"/api/campaigns/{c.id}/streams")).json()


@respx.mock
async def test_fetch_gone_410(auth_client, session):
    c, _ = await _setup(session, kt_id=1)
    _mock_fetch([], campaign_status=404)
    r = await auth_client.post(f"/api/campaigns/{c.id}/fetch")
    assert r.status_code == 410
    assert r.json() == {"detail": "Campaign was deleted in Keitaro"}


async def test_fetch_unknown_campaign_404(auth_client):
    r = await auth_client.post(f"/api/campaigns/{uuid.uuid4()}/fetch")
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/campaigns/{u}/fetch", None),
        ("POST", "/streams/{u}/offers", {"offer_id": 1}),
        ("DELETE", "/streams/{u}/offers/1", None),
        ("PATCH", "/streams/{u}/offers/1", {"pinned": True}),
        ("POST", "/campaigns/{u}/cancel", None),
        ("POST", "/campaigns/{u}/push", None),
    ],
)
async def test_requires_auth(client, method, path, body):
    r = await client.request(method, "/api" + path.format(u=uuid.uuid4()), json=body)
    assert r.status_code == 401


async def test_remove_never_synced_offer_deletes_it(auth_client, session):
    _, s = await _setup(session)
    await _add(auth_client, s, 4)
    r = await auth_client.delete(f"/api/streams/{s.id}/offers/4")
    assert r.status_code == 200
    body = r.json()
    assert 4 not in _shares(body)  # gone, not a grey "removed" row
    assert _shares(body) == {1: 34, 2: 33, 3: 33}
    assert body["dirty"] is False


async def test_cancel_drops_never_synced_offers(auth_client, session):
    c, s = await _setup(session)
    await _add(auth_client, s, 4)
    r = await auth_client.post(f"/api/campaigns/{c.id}/cancel")
    body = r.json()["streams"][0]
    assert [o["offer_id"] for o in body["offers"]] == [1, 2, 3]
    assert body["dirty"] is False


async def test_offer_once_in_keitaro_stays_as_removed(auth_client, session):
    # D was in Keitaro and removed there (inactive, seen_in_kt): Bring back
    # then Remove again keeps its grey history row
    c, s = await _setup(session)
    from tests.test_streams_api import _so

    session.add(_so(s, 4, 3, 0, active=False, synced=(False, 0)))
    await session.commit()
    await _add(auth_client, s, 4)
    r = await auth_client.delete(f"/api/streams/{s.id}/offers/4")
    d = next(o for o in r.json()["offers"] if o["offer_id"] == 4)
    assert d["active"] is False and d["share"] == 0
    r = await auth_client.post(f"/api/campaigns/{c.id}/cancel")
    assert 4 in [o["offer_id"] for o in r.json()["streams"][0]["offers"]]


@respx.mock
async def test_push_skips_clean_streams(auth_client, session):
    # second offer stream is untouched: only the changed one goes to Keitaro
    c, s = await _setup(session)
    await _seed_stream(session, c, [(2, 0, 100, True, {})], kt_id=11, position=3)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    put = respx.put(f"{API}/streams/{STREAM_KT_ID}").respond(json={"id": 10})
    other = respx.put(f"{API}/streams/11").respond(json={"id": 11})
    respx.get(f"{API}/campaigns/77").respond(json={"id": 77})
    respx.get(f"{API}/campaigns/77/streams").respond(
        json=[KT_BEFORE, _kt_stream(11, [(2, 100)], position=3)]
    )
    r = await auth_client.post(f"/api/campaigns/{c.id}/push")
    assert r.status_code == 200
    assert put.call_count == 1 and other.call_count == 0


async def test_push_unknown_campaign_404(auth_client):
    r = await auth_client.post(f"/api/campaigns/{uuid.uuid4()}/push")
    assert r.status_code == 404


@pytest.mark.parametrize(
    "in_kt",
    [
        # someone added an offer to the stream in Keitaro
        [_kt_stream(STREAM_KT_ID, [(1, 25), (2, 25), (3, 25), (9, 25)])],
        # someone changed a share in Keitaro
        [_kt_stream(STREAM_KT_ID, [(1, 50), (2, 25), (3, 25)])],
        # someone deleted the stream in Keitaro
        [],
    ],
)
@respx.mock
async def test_push_refuses_when_stream_changed_in_kt(auth_client, session, in_kt):
    c, s = await _setup(session)
    await auth_client.delete(f"/api/streams/{s.id}/offers/1")
    respx.get(f"{API}/campaigns/77/streams").respond(json=in_kt)
    put = respx.put(f"{API}/streams/{STREAM_KT_ID}").respond(json={"id": 10})
    r = await auth_client.post(f"/api/campaigns/{c.id}/push")
    assert r.status_code == 409
    assert r.json() == {
        "detail": "A stream was changed in Keitaro. Press Cancel, then Fetch from KT"
    }
    assert put.call_count == 0
    session.expire_all()
    rows = {r.kt_offer_id: r for r in await session.scalars(select(StreamOffer))}
    assert rows[1].active is False and rows[2].share == 50  # draft kept
