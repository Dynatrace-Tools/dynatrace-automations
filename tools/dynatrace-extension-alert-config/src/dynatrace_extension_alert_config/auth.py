from __future__ import annotations
import time
from typing import Optional

import requests

TOKEN_URL = "https://sso.dynatrace.com/sso/oauth2/token"

# Only the validated Settings 2.0 scopes are requested by default. These are
# sufficient to read the metric-events schema and create detectors. Requesting
# a scope the OAuth client was not granted makes Dynatrace SSO reject the WHOLE
# token request with HTTP 400, so we keep this list minimal and let callers add
# more via --scopes if their client has them.
REQUIRED_SCOPES = (
    "settings:schemas:read "
    "settings:objects:read "
    "settings:objects:write"
)

_token_cache: dict[str, tuple[str, float]] = {}


def get_bearer_token(creds: dict, scopes: str = REQUIRED_SCOPES) -> str:
    cache_key = f"{creds['clientId']}::{scopes}"
    if cache_key in _token_cache:
        token, expires_at = _token_cache[cache_key]
        if time.time() < expires_at - 30:
            return token

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
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
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("error") or resp.text
        except ValueError:
            detail = resp.text
        raise AuthError(
            f"OAuth 400 Bad Request: {detail}\n"
            f"Requested scopes: {scopes}\n"
            "A 400 here usually means one of the requested scopes is invalid or "
            "was not granted to this OAuth client. Verify in Dynatrace under "
            "Account Management → Identity & access management → OAuth clients that "
            "the client has: settings:schemas:read, settings:objects:read, "
            "settings:objects:write. Also confirm the 'resource' is your account "
            "URN (urn:dtaccount:<uuid>)."
        )
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
