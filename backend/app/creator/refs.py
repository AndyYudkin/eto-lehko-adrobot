import asyncio
from dataclasses import dataclass

from app.config import Settings
from app.keitaro.client import KeitaroClient, KeitaroError

GROUP_TYPE_CAMPAIGNS = "campaigns"


class ConfigError(Exception):
    """User-facing configuration problem (message is shown as is)."""


@dataclass(frozen=True)
class Refs:
    domain_id: int
    domain_name: str
    domain_is_ssl: bool
    group_id: int
    traffic_source_id: int


def campaign_url(refs: Refs, alias: str) -> str:
    scheme = "https://" if refs.domain_is_ssl else "http://"
    return f"{scheme}{refs.domain_name}/{alias}"


def _checked(item: dict, kind: str) -> dict:
    """The picked entity must have an int id and a str name, else Keitaro is off."""
    item_id = item.get("id")
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        raise KeitaroError(0, f"{kind}: id is not an integer")
    if not isinstance(item.get("name"), str):
        raise KeitaroError(0, f"{kind}: name is not a string")
    return item


def _norm_domain(value: str) -> str:
    v = value.strip()
    for prefix in ("https://", "http://"):
        if v.lower().startswith(prefix):
            v = v[len(prefix) :]
    return v.strip("/").lower()


def _pick_domain(domains: list[dict], wanted: str | None) -> dict:
    if not wanted or not _norm_domain(wanted):
        for d in domains:
            if d.get("state") == "active":
                return d
        raise ConfigError("В Keitaro нет активных доменов")
    target = _norm_domain(wanted)
    for d in domains:
        if _norm_domain(d.get("name") or "") == target:
            if d.get("state") != "active":
                raise ConfigError(f"Домен {wanted} в Keitaro не активен")
            return d
    raise ConfigError(f"В Keitaro нет домена {wanted}")


async def resolve_refs(kt: KeitaroClient, settings: Settings) -> Refs:
    if not settings.kt_group:
        raise ConfigError("Не задана переменная окружения KT_GROUP")
    if not settings.kt_traffic_source:
        raise ConfigError("Не задана переменная окружения KT_TRAFFIC_SOURCE")

    domains, groups, sources = await asyncio.gather(
        kt.list_domains(),
        kt.list_groups(GROUP_TYPE_CAMPAIGNS),
        kt.list_traffic_sources(),
    )

    domain = _checked(_pick_domain(domains, settings.kt_domain), "domain")

    group = next(
        (
            g
            for g in groups
            if g.get("type") == GROUP_TYPE_CAMPAIGNS
            and g.get("name") == settings.kt_group
        ),
        None,
    )
    if group is None:
        raise ConfigError(f"В Keitaro нет группы {settings.kt_group}")
    _checked(group, "group")

    source = next(
        (s for s in sources if s.get("name") == settings.kt_traffic_source), None
    )
    if source is None:
        raise ConfigError(f"В Keitaro нет источника {settings.kt_traffic_source}")
    if source.get("state") != "active":
        raise ConfigError(f"Источник {settings.kt_traffic_source} в Keitaro не активен")
    _checked(source, "traffic source")

    return Refs(
        domain_id=domain["id"],
        domain_name=domain["name"],
        domain_is_ssl=bool(domain.get("is_ssl")),
        group_id=group["id"],
        traffic_source_id=source["id"],
    )
