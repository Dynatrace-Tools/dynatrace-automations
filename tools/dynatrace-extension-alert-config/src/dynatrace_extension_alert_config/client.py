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


def _violations_text(error_obj: dict) -> str:
    """Render an error object's message plus any constraint violations."""
    msg = error_obj.get("message", "") or ""
    violations = error_obj.get("constraintViolations") or []
    parts = []
    for v in violations:
        path = v.get("path") or v.get("parameterLocation") or ""
        vmsg = v.get("message", "")
        parts.append(f"{path}: {vmsg}".strip(": "))
    if parts:
        msg = f"{msg} ({'; '.join(parts)})" if msg else "; ".join(parts)
    return msg


def _extract_error(resp: requests.Response) -> DynatraceApiError:
    """Build a DynatraceApiError from a failed response.

    Handles both shapes Dynatrace returns:
    - dict: {"error": {"message": ..., "constraintViolations": [...]}}
    - list: the Settings 2.0 objects API returns an ARRAY of per-object results,
      each like {"code": 400, "error": {...}} — calling .get() on the list
      directly was the source of "'list' object has no attribute 'get'".
    Also pulls out a 'missing required scope. Use one of: ...' hint when present.
    """
    body_text = resp.text
    message = body_text
    try:
        body = resp.json()
    except ValueError:
        body = None

    if isinstance(body, dict):
        message = _violations_text(body.get("error", {})) or body.get("message") or body_text
    elif isinstance(body, list):
        msgs = []
        for item in body:
            if isinstance(item, dict) and "error" in item:
                msgs.append(_violations_text(item["error"]) or str(item))
        message = " | ".join(m for m in msgs if m) or body_text

    required: list[str] = []
    # e.g. "Token is missing required scope. Use one of: [extensions.read, ...]"
    m = re.search(r"required scope.*?:\s*\[?([^\]\n]+)\]?", message, re.IGNORECASE)
    if m:
        required = [s.strip() for s in re.split(r"[,\s]+", m.group(1)) if s.strip()]

    return DynatraceApiError(resp.status_code, message, required)


class DynatraceClient:
    def __init__(self, env_url: str, token_provider) -> None:
        """``token_provider`` is a no-arg callable returning a valid bearer
        token. It is invoked per request so a token that expires during a long
        interactive session is transparently refreshed (the auth layer caches
        and re-issues as needed). A plain token string is also accepted.
        """
        self._base = env_url.rstrip("/")
        if callable(token_provider):
            self._token_provider = token_provider
        else:
            self._token_provider = lambda: token_provider
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _auth_header(self, extra: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self._token_provider()}"}
        if extra:
            headers.update(extra)
        return headers

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = self._session.get(
            f"{self._base}{path}", params=params, headers=self._auth_header(), timeout=30
        )
        if not resp.ok:
            raise _extract_error(resp)
        return resp.json()

    def _post(self, path: str, json_body: Any) -> Any:
        resp = self._session.post(
            f"{self._base}{path}", json=json_body, headers=self._auth_header(), timeout=30
        )
        if not resp.ok:
            raise _extract_error(resp)
        return resp.json()

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_schema(self, schema_id: str) -> dict:
        return self._get(f"/api/v2/settings/schemas/{schema_id}")

    def create_settings_object(self, payload: dict) -> str:
        """Create a single settings object, returning its objectId.

        The Settings 2.0 objects API returns HTTP 200 with an array of per-object
        results even when an individual object fails validation, so we inspect
        the item's ``code`` rather than trusting the HTTP status alone.
        """
        results = self._post("/api/v2/settings/objects", [payload])
        if not isinstance(results, list) or not results:
            raise DynatraceApiError(0, f"Unexpected response: {results}")
        item = results[0]
        code = item.get("code")
        if isinstance(code, int) and 200 <= code < 300:
            return item.get("objectId", "")
        message = _violations_text(item.get("error", {})) or str(item)
        raise DynatraceApiError(code or 400, message)

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
            headers=self._auth_header({"Accept": "application/octet-stream"}),
            timeout=60,
        )
        if not resp.ok:
            raise _extract_error(resp)
        return resp.content
