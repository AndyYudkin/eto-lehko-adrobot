import logging
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy import select

from app.auth.service import seed_user
from app.config import get_settings
from app.keitaro.client import KeitaroClient, KeitaroError
from app.models import Offer
from app.offers.sync import sync_offers

KT = "http://kt.test"


@pytest.fixture
def kt_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "kt_url", KT)
    monkeypatch.setattr(s, "kt_api_key", "test-key")


async def _offers(session):
    session.expire_all()
    rows = (await session.execute(select(Offer).order_by(Offer.kt_id))).scalars()
    return [(o.kt_id, o.name, o.state) for o in rows]


async def _seed(session):
    now = datetime.now(UTC)
    session.add_all(
        [
            Offer(kt_id=1, name="A", state="active", synced_at=now),
            Offer(kt_id=2, name="B", state="active", synced_at=now),
        ]
    )
    await session.commit()


@respx.mock
async def test_sync_offers(session):
    await _seed(session)
    route = respx.get(f"{KT}/admin_api/v1/offers").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": 2, "name": "B2", "state": "disabled", "archive": "x"},
                {"id": 3, "name": "C", "state": "active"},
            ],
        )
    )
    await sync_offers(session, KeitaroClient(KT, "test-key"))
    assert route.calls.last.request.headers["Api-Key"] == "test-key"
    assert await _offers(session) == [
        (2, "B2", "disabled"),
        (3, "C", "active"),
    ]


@respx.mock
async def test_sync_offers_kt_error_keeps_table(session):
    await _seed(session)
    respx.get(f"{KT}/admin_api/v1/offers").mock(return_value=httpx.Response(500))
    with pytest.raises(KeitaroError):
        await sync_offers(session, KeitaroClient(KT, "test-key"))
    assert await _offers(session) == [(1, "A", "active"), (2, "B", "active")]


async def _login(client, password="test-password"):
    return await client.post(
        "/api/auth/login", json={"login": "admin", "password": password}
    )


@respx.mock
async def test_login_triggers_offer_sync(client, session, kt_configured):
    await seed_user(session, "admin", "test-password")
    respx.get(f"{KT}/admin_api/v1/offers").mock(
        return_value=httpx.Response(
            200, json=[{"id": 7, "name": "X", "state": "active"}]
        )
    )
    assert (await _login(client)).status_code == 204
    assert await _offers(session) == [(7, "X", "active")]


@respx.mock
async def test_wrong_password_no_kt_call(client, session, kt_configured):
    await seed_user(session, "admin", "test-password")
    route = respx.get(f"{KT}/admin_api/v1/offers").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert (await _login(client, "wrong")).status_code == 401
    assert not route.called


@respx.mock
async def test_login_survives_kt_down(client, session, kt_configured):
    await seed_user(session, "admin", "test-password")
    await _seed(session)
    respx.get(f"{KT}/admin_api/v1/offers").mock(return_value=httpx.Response(500))
    assert (await _login(client)).status_code == 204
    assert await _offers(session) == [(1, "A", "active"), (2, "B", "active")]


async def test_kt_not_configured(client, session, caplog):
    await seed_user(session, "admin", "test-password")
    with caplog.at_level(logging.WARNING):
        assert (await _login(client)).status_code == 204
    assert "not configured" in caplog.text


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"error": "not a list"}),
        httpx.Response(200, json=[{"id": 5, "name": "no state"}]),
        httpx.Response(200, json=[{"id": "5", "name": "E", "state": "active"}]),
        httpx.Response(200, json=[{"id": 5, "name": None, "state": "active"}]),
    ],
    ids=["not-json", "not-a-list", "missing-state", "id-not-int", "name-null"],
)
@respx.mock
async def test_sync_offers_bad_payload_keeps_table(session, response):
    await _seed(session)
    respx.get(f"{KT}/admin_api/v1/offers").mock(return_value=response)
    with pytest.raises(KeitaroError):
        await sync_offers(session, KeitaroClient(KT, "test-key"))
    assert await _offers(session) == [(1, "A", "active"), (2, "B", "active")]


@respx.mock
async def test_sync_offers_safe_logs_one_line_on_bad_payload(
    session, kt_configured, caplog
):
    from app.offers.sync import sync_offers_safe

    await _seed(session)
    respx.get(f"{KT}/admin_api/v1/offers").mock(
        return_value=httpx.Response(200, json=[{"id": 5}])
    )
    with caplog.at_level(logging.WARNING):
        await sync_offers_safe()  # must not raise
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].exc_info is None
    assert await _offers(session) == [(1, "A", "active"), (2, "B", "active")]
