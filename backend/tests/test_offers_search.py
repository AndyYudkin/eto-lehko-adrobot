from datetime import UTC, datetime

import pytest
import respx

from app.models import Offer


@pytest.fixture(autouse=True)
def _no_keitaro():
    # no routes registered: any Keitaro call raises
    with respx.mock(assert_all_called=False):
        yield


async def _seed(session, rows):
    for kt_id, name, state in rows:
        session.add(
            Offer(
                kt_id=kt_id,
                name=name,
                state=state,
                synced_at=datetime.now(UTC),
            )
        )
    await session.commit()


ROWS = [
    (11111, "FitoMishki [Weight Loss]", "active"),
    (18813, "Flexacil [JOINT-PE]", "active"),
    (22222, "Fito Disabled", "disabled"),
    (33333, "Promo 50% off", "active"),
    (44444, "Promo 50 other", "active"),
]


async def test_search_by_name_case_insensitive(auth_client, session):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": "fito"})
    assert r.status_code == 200
    assert r.json() == [{"id": 11111, "name": "FitoMishki [Weight Loss]"}]


async def test_search_by_id(auth_client, session):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": "18813"})
    assert r.json() == [{"id": 18813, "name": "Flexacil [JOINT-PE]"}]


async def test_partial_id_matches_name_only(auth_client, session):
    await _seed(session, ROWS + [(5, "Has 188 inside", "active")])
    r = await auth_client.get("/api/offers", params={"q": "188"})
    assert r.json() == [{"id": 5, "name": "Has 188 inside"}]


async def test_disabled_never_returned(auth_client, session):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": "22222"})
    assert r.json() == []


@pytest.mark.parametrize("q", ["", "  "])
async def test_blank_query_is_empty(auth_client, session, q):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": q})
    assert r.status_code == 200
    assert r.json() == []


async def test_percent_is_not_wildcard(auth_client, session):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": "50%"})
    assert [o["id"] for o in r.json()] == [33333]


async def test_underscore_is_not_wildcard(auth_client, session):
    await _seed(session, ROWS)
    r = await auth_client.get("/api/offers", params={"q": "F_to"})
    assert r.json() == []


async def test_requires_auth(client):
    r = await client.get("/api/offers", params={"q": "fito"})
    assert r.status_code == 401


async def _stream_with(session, offers):
    """A campaign with one offer stream holding (kt_offer_id, active) rows."""
    import uuid

    from app.models import Campaign, Stream, StreamOffer

    c = Campaign(kt_id=1, name="c", alias="a", url="http://x/a", geo=["MX"], offer_id=1)
    session.add(c)
    await session.flush()
    s = Stream(
        id=uuid.uuid4(),
        campaign_id=c.id,
        kt_id=10,
        name="Offer",
        position=2,
        type="regular",
        schema="landings",
        has_offers=True,
        filters=[],
        action_payload=None,
    )
    session.add(s)
    await session.flush()
    for i, (oid, active) in enumerate(offers):
        session.add(
            StreamOffer(
                stream_id=s.id,
                kt_offer_id=oid,
                name=str(oid),
                position=i + 1,
                synced_active=active,
                synced_share=100 if active else 0,
                active=active,
                share=100 if active else 0,
            )
        )
    await session.commit()
    return s.id


async def test_exclude_stream_hides_offers_already_in_it(auth_client, session):
    await _seed(session, ROWS)
    # 11111 active in the stream, 33333 removed (inactive) — both hidden
    sid = await _stream_with(session, [(11111, True), (33333, False)])
    r = await auth_client.get(
        "/api/offers", params={"q": "o", "exclude_stream": str(sid)}
    )
    assert r.status_code == 200
    ids = [o["id"] for o in r.json()]
    assert 11111 not in ids and 33333 not in ids
    assert 18813 in ids and 44444 in ids
    # without the parameter nothing is excluded
    r = await auth_client.get("/api/offers", params={"q": "o"})
    assert {11111, 33333} <= {o["id"] for o in r.json()}


async def test_exclude_unknown_stream_404(auth_client, session):
    import uuid

    r = await auth_client.get(
        "/api/offers", params={"q": "o", "exclude_stream": str(uuid.uuid4())}
    )
    assert r.status_code == 404
