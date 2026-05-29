from __future__ import annotations
import time
from typing import Optional

import requests

TOKEN_URL = "https://sso.dynatrace.com/sso/oauth2/token"
REQUIRED_SCOPES = (
    "settings:objects:read "
    "settings:objects:write "
    "settings:schemas:read "
    "extensions:read "
    "extensions.environment:read"
)

_token_cache: dict[str, tuple[str, float]] = {}


def get_bearer_token(creds: dict, scopes: str = REQUIRED_SCOPES) -> str:
    cache_key = creds["clientId"]
    if cache_key in _token_cache:
        token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at - 30:
            return token

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": creds["clientId"],
            "client_secret": creds["clientSecret"],
            "resource": creds["resource"],
            "scope": scopes,
        },
        timeout=30,
    )

    if resp.status_code == 400:
        detail = resp.json().get("error_description", resp.text)
        raise AuthError(f"OAuth 400 Bad Request: {detail}")
    if resp.status_code == 401:
        raise AuthError("OAuth 401 Unauthorized — check your Client ID and Client Secret.")
    resp.raise_for_status()

    data = resp.json()
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 300))
    _token_cache[cache_key] = (token, time.time() + expires_in)
    return token


class AuthError(Exception):
    pass
