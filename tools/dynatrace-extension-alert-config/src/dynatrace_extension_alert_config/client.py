from __future__ import annotations
import re
from typing import Any, Optional

import requests


class DynatraceApiError(Exception):
    """A Dynatrace API error that carries the server's message and any
    required-scope hint parsed from the response body."""

    def __init__(self, status: int, message: str, required_scopes: Optional[list[str]] = None):
        self.status = status
        self.message = message
        self.required_scopes = required_scopes or []
        super().__init__(message)


def _extract_error(resp: requests.Response) -> DynatraceApiError:
    """Build a DynatraceApiError from a failed response, pulling out the
    'missing required scope. Use one of: ...' hint when present."""
    body_text = resp.text
    message = body_text
    try:
        err = resp.json().get("error", {})
        message = err.get("message", body_text)
    except ValueError:
        pass

    required: list[str] = []
    # e.g. "Token is missing required scope. Use one of: [extensions.read, ...]"
    m = re.search(r"required scope.*?:\s*\[?([^\]\n]+)\]?", message, re.IGNORECASE)
    if m:
        required = [s.strip() for s in re.split(r"[,\s]+", m.group(1)) if s.strip()]

    return DynatraceApiError(resp.status_code, message, required)


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
        if not resp.ok:
            raise _extract_error(resp)
        return resp.json()

    def _post(self, path: str, json_body: Any) -> Any:
        resp = self._session.post(f"{self._base}{path}", json=json_body, timeout=30)
        if not resp.ok:
            raise _extract_error(resp)
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

    def download_extension(self, ext_name: str, version: str) -> bytes:
        """Download the raw extension .zip (contains extension.yaml)."""
        resp = self._session.get(
            f"{self._base}/api/v2/extensions/{ext_name}/{version}",
            headers={"Accept": "application/octet-stream"},
            timeout=60,
        )
        if not resp.ok:
            raise _extract_error(resp)
        return resp.content
