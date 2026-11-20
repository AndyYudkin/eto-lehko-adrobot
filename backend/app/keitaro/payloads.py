GOOGLE_URL = "https://google.com"
ACTION_TYPE_HTTP = "http"
SCHEMA_REDIRECT = "redirect"
SCHEMA_LANDINGS = "landings"
FILTER_COUNTRY = "country"


def campaign_payload(
    name: str, alias: str, domain_id: int, group_id: int, source_id: int
) -> dict:
    return {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "domain_id": domain_id,
        "group_id": group_id,
        "traffic_source_id": source_id,
    }


def geo_stream_payload(campaign_id: int, geo: list[str]) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Geo → Google",
        "position": 1,
        "state": "active",
        "schema": SCHEMA_REDIRECT,
        "action_type": ACTION_TYPE_HTTP,
        "action_payload": GOOGLE_URL,
        "filters": [{"name": FILTER_COUNTRY, "mode": "accept", "payload": geo}],
    }


def offer_stream_payload(campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Offer",
        "position": 2,
        "state": "active",
        "schema": SCHEMA_LANDINGS,
        "action_type": ACTION_TYPE_HTTP,  # required by Keitaro even for offers
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def offers_update_payload(offers: list[tuple[int, int]]) -> dict:
    """offers: (offer_id, share) of the active offers."""
    return {
        "offers": [
            {"offer_id": oid, "share": share, "state": "active"}
            for oid, share in offers
        ]
    }
