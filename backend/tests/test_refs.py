import httpx
import pytest
import respx
from fastapi import FastAPI

from app.config import Settings
from app.creator.refs import ConfigError, campaign_url, resolve_refs
from app.errors import register_error_handlers
from app.keitaro.client import KeitaroClient, KeitaroError

KT = "http://kt.test"

DOMAINS = [
    {"id": 1, "name": "other.com", "state": "active", "is_ssl": True},
    {"id": 1813, "name": "kylovoa.com", "state": "active", "is_ssl": False},
]
GROUPS = [
    {"id": 5, "name": "FORTESTS", "type": "offers"},
    {"id": 10332, "name": "FORTESTS", "type": "campaigns"},
]
SOURCES = [
    {"id": 835, "name": "Other", "state": "active"},
    {"id": 836, "name": "Src", "state": "active"},
]


def _settings(**kw) -> Settings:
    base = dict(
        database_url="x",
        app_login="a",
        app_password="b",
        jwt_secret="c",
        kt_domain="https://KYLOVOA.com/",
        kt_group="FORTESTS",
        kt_traffic_source="Src",
    )
    base.update(kw)
    return Settings(_env_file=None, **base)


def _mock(domains=DOMAINS, groups=GROUPS, sources=SOURCES):
    d = respx.get(f"{KT}/admin_api/v1/domains").respond(json=domains)
    g = respx.get(f"{KT}/admin_api/v1/groups").respond(json=groups)
    s = respx.get(f"{KT}/admin_api/v1/traffic_sources").respond(json=sources)
    return d, g, s


@respx.mock
async def test_resolve_refs():
    _, g, _ = _mock()
    refs = await resolve_refs(KeitaroClient(KT, "k"), _settings())
    assert (refs.domain_id, refs.domain_name) == (1813, "kylovoa.com")
    assert refs.domain_is_ssl is False
    assert refs.group_id == 10332
    assert refs.traffic_source_id == 836
    assert g.calls.last.request.url.params["type"] == "campaigns"
    assert campaign_url(refs, "abc").startswith("http://")
    assert campaign_url(refs, "abc") == "http://kylovoa.com/abc"


@respx.mock
async def test_empty_domain_picks_first_active():
    domains = [
        {"id": 1, "name": "a.com", "state": "disabled", "is_ssl": True},
        {"id": 2, "name": "b.com", "state": "active", "is_ssl": True},
        {"id": 3, "name": "c.com", "state": "active", "is_ssl": True},
    ]
    _mock(domains=domains)
    refs = await resolve_refs(KeitaroClient(KT, "k"), _settings(kt_domain=""))
    assert refs.domain_id == 2
    assert campaign_url(refs, "x") == "https://b.com/x"


@pytest.mark.parametrize(
    "kw, mock_kw, needle",
    [
        ({"kt_domain": "nope.com"}, {}, "nope.com"),
        (
            {},
            {
                "domains": [
                    {
                        "id": 1,
                        "name": "kylovoa.com",
                        "state": "disabled",
                        "is_ssl": True,
                    }
                ]
            },
            "(?i)kylovoa.com",
        ),
        ({"kt_group": "NOGROUP"}, {}, "NOGROUP"),
        ({"kt_traffic_source": "NoSrc"}, {}, "NoSrc"),
        (
            {},
            {"sources": [{"id": 836, "name": "Src", "state": "disabled"}]},
            "Src",
        ),
    ],
)
@respx.mock
async def test_missing_refs_error(kw, mock_kw, needle):
    _mock(**mock_kw)
    with pytest.raises(ConfigError, match=needle):
        await resolve_refs(KeitaroClient(KT, "k"), _settings(**kw))
    assert all(c.request.method == "GET" for c in respx.calls)


@respx.mock
async def test_missing_env_vars():
    _mock()
    with pytest.raises(ConfigError, match="KT_GROUP"):
        await resolve_refs(KeitaroClient(KT, "k"), _settings(kt_group=None))


async def test_error_handlers():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/cfg")
    async def cfg():
        raise ConfigError("В Keitaro нет группы X")

    @app.get("/kt")
    async def kt():
        raise KeitaroError(500, "b" * 500)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        r = await c.get("/cfg")
        assert (r.status_code, r.json()) == (400, {"detail": "В Keitaro нет группы X"})
        r = await c.get("/kt")
        assert r.status_code == 502
        assert r.json()["detail"].startswith("Keitaro error: ")
        assert len(r.json()["detail"]) < 300


ERROR_BODY = {"error": "Param 'type' is required", "stacktrace": None}


@pytest.mark.parametrize(
    "bad",
    [
        {"domains": ERROR_BODY},
        {"groups": ERROR_BODY},
        {"sources": ERROR_BODY},
        {"domains": ["kylovoa.com"]},
        {"groups": [{"name": "FORTESTS", "type": "campaigns"}]},  # no id
        {"sources": [{"id": "836", "name": "Src", "state": "active"}]},  # str id
        {"domains": [{"id": 1813, "state": "active", "is_ssl": True}]},  # no name
    ],
    ids=[
        "domains-error-object",
        "groups-error-object",
        "sources-error-object",
        "domain-item-not-dict",
        "group-without-id",
        "source-id-not-int",
        "domain-without-name",
    ],
)
@respx.mock
async def test_unexpected_payload_is_keitaro_error(bad):
    _mock(**bad)
    with pytest.raises(KeitaroError):
        await resolve_refs(
            KeitaroClient(KT, "k"),
            _settings(kt_domain="" if "domains" in bad else "kylovoa.com"),
        )
