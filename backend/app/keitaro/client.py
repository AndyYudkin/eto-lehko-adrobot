import httpx

from app.config import get_settings


class KeitaroError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Keitaro error {status}: {body[:200]}")
        self.status = status
        self.body = body


class KeitaroNotFound(KeitaroError):
    pass


class KeitaroClient:
    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._http = http

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        if not self._base_url or not self._api_key:
            raise KeitaroError(0, "Keitaro is not configured")
        url = f"{self._base_url.rstrip('/')}/admin_api/v1{path}"
        headers = {"Api-Key": self._api_key}
        try:
            if self._http is not None:
                resp = await self._http.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=10,
                )
            else:
                async with httpx.AsyncClient(timeout=10) as http:
                    resp = await http.request(
                        method, url, headers=headers, params=params, json=json
                    )
        except httpx.HTTPError as exc:
            raise KeitaroError(0, str(exc)) from exc
        if resp.status_code == 404:
            raise KeitaroNotFound(404, resp.text)
        if resp.status_code >= 400:
            raise KeitaroError(resp.status_code, resp.text)
        return resp

    async def _json(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ):
        resp = await self._request(method, path, params, json)
        try:
            return resp.json()
        except ValueError as exc:
            raise KeitaroError(resp.status_code, "invalid JSON in response") from exc

    async def list_offers(self) -> list[dict]:
        return await self._json("GET", "/offers")

    async def _json_list(self, path: str, params: dict | None = None) -> list[dict]:
        """GET a list of objects; Keitaro sometimes answers with an error object."""
        data = await self._json("GET", path, params)
        if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
            raise KeitaroError(0, f"{path}: expected a list of objects")
        return data

    async def list_domains(self) -> list[dict]:
        return await self._json_list("/domains")

    async def list_groups(self, type: str = "campaigns") -> list[dict]:
        return await self._json_list("/groups", {"type": type})

    async def list_traffic_sources(self) -> list[dict]:
        return await self._json_list("/traffic_sources")

    async def get_campaign_streams(self, kt_id: int) -> list[dict]:
        return await self._json_list(f"/campaigns/{kt_id}/streams")

    async def _create(self, path: str, payload: dict) -> dict:
        data = await self._json("POST", path, json=payload)
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("id"), int)
            or isinstance(data.get("id"), bool)
        ):
            raise KeitaroError(0, f"{path}: expected an object with an int id")
        return data

    async def create_campaign(self, payload: dict) -> dict:
        return await self._create("/campaigns", payload)

    async def create_stream(self, payload: dict) -> dict:
        return await self._create("/streams", payload)

    async def get_campaign(self, campaign_id: int) -> dict:
        """404 (KeitaroNotFound) also for archived campaigns, whose streams
        are still served — so this, not the streams call, tells if it's gone."""
        data = await self._json("GET", f"/campaigns/{campaign_id}")
        if not isinstance(data, dict):
            raise KeitaroError(0, f"/campaigns/{campaign_id}: expected an object")
        return data

    async def update_stream(self, kt_id: int, payload: dict) -> None:
        # request format unverified on the live instance: fix it here
        await self._request("PUT", f"/streams/{kt_id}", json=payload)

    async def delete_campaign(self, campaign_id: int) -> None:
        await self._request("DELETE", f"/campaigns/{campaign_id}")


def get_kt() -> KeitaroClient:
    s = get_settings()
    return KeitaroClient(s.kt_url, s.kt_api_key)
