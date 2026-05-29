from __future__ import annotations
from typing import Any, Optional

import requests


class DynatraceClient:
    def __init__(self, env_url: str, token: str) -> None:
        self._base = env_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = self._session.get(f"{self._base}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: Any) -> Any:
        resp = self._session.post(f"{self._base}{path}", json=json_body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_schema(self, schema_id: str) -> dict:
        return self._get(f"/api/v2/settings/schemas/{schema_id}")

    def create_settings_objects(self, payloads: list[dict]) -> list[dict]:
        return self._post("/api/v2/settings/objects", payloads)

    def list_settings_objects(self, schema_id: str) -> list[dict]:
        data = self._get("/api/v2/settings/objects", params={"schemaIds": schema_id})
        return data.get("items", [])

    # ── Extensions 2.0 ────────────────────────────────────────────────────────

    def list_extensions(self) -> list[dict]:
        """Return all installed extensions (name, version metadata only)."""
        results: list[dict] = []
        next_page: Optional[str] = None
        while True:
            params: dict = {"pageSize": 100}
            if next_page:
                params["nextPageKey"] = next_page
            data = self._get("/api/v2/extensions", params=params)
            results.extend(data.get("extensions", []))
            next_page = data.get("nextPageKey")
            if not next_page:
                break
        return results

    def get_extension_monitoring_configurations(self, ext_name: str) -> list[dict]:
        data = self._get(f"/api/v2/extensions/{ext_name}/monitoringConfigurations")
        return data.get("items", [])

    def get_extension_schema(self, ext_name: str, version: str) -> dict:
        return self._get(f"/api/v2/extensions/{ext_name}/{version}")

    def get_extension_environment_config(self, ext_name: str) -> dict:
        return self._get(f"/api/v2/extensions/{ext_name}/environmentConfiguration")
