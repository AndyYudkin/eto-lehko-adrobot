import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from app.config import get_settings
from app.models import Campaign, Offer, Stream

KT = "http://kt.test"
API = f"{KT}/admin_api/v1"

DOMAINS = [{"id": 1813, "name": "kylovoa.com", "state": "active", "is_ssl": True}]
GROUPS = [{"id": 10332, "name": "FORTESTS", "type": "campaigns"}]
SOURCES = [{"id": 836, "name": "Src", "state": "active"}]


@pytest.fixture(autouse=True)
def _kt_settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "kt_url", KT)
    monkeypatch.setattr(s, "kt_api_key", "key")
    monkeypatch.setattr(s, "kt_domain", "kylovoa.com")
    monkeypatch.setattr(s, "kt_group", "FORTESTS")
    monkeypatch.setattr(s, "kt_traffic_source", "Src")
    monkeypatch.setattr(s, "campaign_name_prefix", "")


async def _seed_offer(session, kt_id=18813, state="active"):
    session.add(
        Offer(
            kt_id=kt_id,
            name="Offer",
            state=state,
            synced_at=datetime.now(UTC),
        )
    )
    await session.commit()


def _mock_refs(groups=GROUPS):
    respx.get(f"{API}/domains").respond(json=DOMAINS)
    respx.get(f"{API}/groups").respond(json=groups)
    respx.get(f"{API}/traffic_sources").respond(json=SOURCES)


def _mock_create(stream_status=(200, 200)):
    camp = respx.post(f"{API}/campaigns").respond(json={"id": 77, "alias": "KtAlias"})
    streams = respx.post(f"{API}/streams").mock(
        side_effect=[
            httpx.Response(stream_status[0], json={"id": 1}),
            httpx.Response(stream_status[1], json={"id": 2}),
        ]
    )
    delete = respx.delete(f"{API}/campaigns/77").respond(json={})
    return camp, streams, delete


def _body(call) -> dict:
    return json.loads(call.request.content)


async def _post(client, **kw):
    data = {"name": "Camp", "geo": ["MX"], "offer_id": 18813}
    data.update(kw)
    return await client.post("/api/campaigns", json=data)


@respx.mock
async def test_geo_normalized(auth_client, session):
    await _seed_offer(session)
    _mock_refs()
    _mock_create()
    r = await _post(auth_client, name="  Camp ", geo=["mx", " AU", "mx"])
    assert r.status_code == 201
    assert r.json()["geo"] == ["MX", "AU"]
    assert r.json()["name"] == "Camp"
    row = (await session.scalars(select(Campaign))).one()
    assert row.geo == ["MX", "AU"]


@pytest.mark.parametrize(
    "kw", [{"geo": ["MEX"]}, {"geo": []}, {"name": ""}, {"name": "   "}]
)
async def test_invalid_input_422(auth_client, kw):
    r = await _post(auth_client, **kw)
    assert r.status_code == 422


@respx.mock
async def test_create_campaign_happy(auth_client, session):
    await _seed_offer(session)
    _mock_refs()
    camp, streams, delete = _mock_create()
    r = await _post(auth_client, geo=["mx", "AU"])
    assert r.status_code == 201
    body = r.json()
    assert body["url"] == "https://kylovoa.com/KtAlias"
    assert body["kt_id"] == 77
    assert body["offer_id"] == 18813

    sent = _body(camp.calls.last)
    alias = sent.pop("alias")
    assert len(alias) == 7 and alias.isalnum()
    assert sent == {
        "name": "Camp",
        "type": "position",
        "state": "active",
        "domain_id": 1813,
        "group_id": 10332,
        "traffic_source_id": 836,
    }
    assert _body(streams.calls[0]) == {
        "campaign_id": 77,
        "type": "regular",
        "name": "Geo → Google",
        "position": 1,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": "https://google.com",
        "filters": [{"name": "country", "mode": "accept", "payload": ["MX", "AU"]}],
    }
    assert _body(streams.calls[1]) == {
        "campaign_id": 77,
        "type": "regular",
        "name": "Offer",
        "position": 2,
        "state": "active",
        "schema": "landings",
        # Keitaro rejects an offers stream without it (422 "Action Type is required")
        "action_type": "http",
        "offers": [{"offer_id": 18813, "share": 100, "state": "active"}],
    }
    assert not delete.called
    row = (await session.scalars(select(Campaign))).one()
    assert (row.kt_id, row.alias, row.offer_id) == (77, "KtAlias", 18813)


@pytest.mark.parametrize("state", [None, "disabled"])
@respx.mock
async def test_invalid_offer_rejected(auth_client, session, state):
    if state:
        await _seed_offer(session, state=state)
    r = await _post(auth_client)
    assert r.status_code == 400
    assert "18813" in r.json()["detail"]
    assert len(respx.calls) == 0


@respx.mock
async def test_missing_refs_400(auth_client, session):
    await _seed_offer(session)
    _mock_refs(groups=[])
    camp, streams, _ = _mock_create()
    r = await _post(auth_client)
    assert r.status_code == 400
    assert "FORTESTS" in r.json()["detail"]
    assert not camp.called and not streams.called


@pytest.mark.parametrize("failing", [0, 1])
@respx.mock
async def test_rollback_on_stream_failure(auth_client, session, failing):
    await _seed_offer(session)
    _mock_refs()
    codes = [200, 200]
    codes[failing] = 500
    _, streams, delete = _mock_create(tuple(codes))
    r = await _post(auth_client)
    assert r.status_code == 502
    assert delete.called
    assert streams.call_count == failing + 1
    assert (await session.scalars(select(Campaign))).all() == []


@respx.mock
async def test_rollback_delete_fails_still_502(auth_client, session):
    await _seed_offer(session)
    _mock_refs()
    _, _, delete = _mock_create((200, 500))
    delete.respond(500)
    r = await _post(auth_client)
    assert r.status_code == 502
    assert delete.called
    assert (await session.scalars(select(Campaign))).all() == []


async def test_list_campaigns(auth_client, session):
    now = datetime.now(UTC)
    for i, name in enumerate(["old", "new"]):
        session.add(
            Campaign(
                kt_id=i + 1,
                name=name,
                alias="a",
                url="http://x/a",
                geo=["MX"],
                offer_id=1,
                created_at=now + timedelta(minutes=i),
            )
        )
    await session.commit()
    r = await auth_client.get("/api/campaigns")
    assert r.status_code == 200
    assert [c["name"] for c in r.json()] == ["new", "old"]


async def test_list_hides_campaigns_deleted_in_keitaro(auth_client, session):
    for i, deleted in enumerate([False, True]):
        session.add(
            Campaign(
                kt_id=i + 1,
                name=f"c{i}",
                alias="a",
                url="http://x/a",
                geo=["MX"],
                offer_id=1,
                kt_deleted=deleted,
            )
        )
    await session.commit()
    r = await auth_client.get("/api/campaigns")
    assert [c["name"] for c in r.json()] == ["c0"]


async def test_campaign_routes_require_auth(client):
    assert (await client.get("/api/campaigns")).status_code == 401
    r = await client.post(
        "/api/campaigns", json={"name": "a", "geo": ["MX"], "offer_id": 1}
    )
    assert r.status_code == 401


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("campaign2", "test_iudkin_campaign2"),
        ("  campaign3 ", "test_iudkin_campaign3"),
        ("test_iudkin_campaign4", "test_iudkin_campaign4"),  # not doubled
    ],
)
@respx.mock
async def test_name_prefix_from_env(auth_client, session, monkeypatch, typed, expected):
    monkeypatch.setattr(get_settings(), "campaign_name_prefix", "test_iudkin_")
    await _seed_offer(session)
    _mock_refs()
    camp, _, _ = _mock_create()
    r = await _post(auth_client, name=typed)
    assert r.status_code == 201
    assert _body(camp.calls.last)["name"] == expected
    assert r.json()["name"] == expected
    row = (await session.scalars(select(Campaign))).one()
    assert row.name == expected


@respx.mock
async def test_create_campaign_syncs_streams(auth_client, session):
    await _seed_offer(session)
    _mock_refs()
    _mock_create()
    respx.get(f"{API}/campaigns/77").respond(json={"id": 77})
    respx.get(f"{API}/campaigns/77/streams").respond(
        json=[
            {
                "id": 1,
                "type": "regular",
                "name": "Geo",
                "position": 1,
                "schema": "redirect",
                "filters": [],
                "offers": [],
            },
            {
                "id": 2,
                "type": "regular",
                "name": "Offers",
                "position": 2,
                "schema": "landings",
                "filters": [],
                "offers": [
                    {"id": 5, "offer_id": 18813, "share": 100, "state": "active"}
                ],
            },
        ]
    )
    r = await _post(auth_client)
    assert r.status_code == 201
    assert r.json()["offers_count"] == 1
    assert len((await session.scalars(select(Stream))).all()) == 2
