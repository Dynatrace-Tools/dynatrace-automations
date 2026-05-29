from __future__ import annotations
import getpass
import json
import os
import stat
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".dynatrace" / "extensions"
CREDS_FILE = CONFIG_DIR / "OAuth.json"

REQUIRED_FIELDS = ("clientId", "clientSecret", "resource", "environmentUrl")


def _ensure_dirs() -> None:
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def load_credentials() -> Optional[dict]:
    if not CREDS_FILE.exists():
        return None
    try:
        creds = json.loads(CREDS_FILE.read_text())
        if all(creds.get(k) for k in REQUIRED_FIELDS):
            return creds
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_credentials(creds: dict) -> None:
    _ensure_dirs()
    CREDS_FILE.write_text(json.dumps(creds, indent=2))
    CREDS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)


def prompt_credentials() -> dict:
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(Panel(
        "[bold cyan]Dynatrace OAuth Configuration[/bold cyan]\n"
        "These credentials are stored at [dim]~/.dynatrace/extensions/OAuth.json[/dim]",
        border_style="cyan",
    ))
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client Secret: ").strip()
    resource = input("Resource (e.g. urn:dtaccount:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx): ").strip()
    env_url = input("Environment URL (e.g. https://<env-id>.live.dynatrace.com): ").strip().rstrip("/")

    creds = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "resource": resource,
        "environmentUrl": env_url,
    }
    save_credentials(creds)
    console.print("[green]Credentials saved.[/green]")
    return creds


def get_or_prompt_credentials(reconfigure: bool = False) -> dict:
    if not reconfigure:
        creds = load_credentials()
        if creds:
            return creds
    return prompt_credentials()
