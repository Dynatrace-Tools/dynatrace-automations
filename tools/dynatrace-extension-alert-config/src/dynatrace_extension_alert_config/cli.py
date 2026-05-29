from __future__ import annotations
import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .anomaly import build_all_payloads
from .auth import AuthError
from .client import DynatraceClient
from .config import get_or_prompt_credentials
from .extensions import ExtensionNotFoundError, resolve_extension
from .interactive import run_auto_flow, run_interactive_flow

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dynatrace-extension-alert-config",
        description="Create Davis Anomaly Detection configurations for Dynatrace extension metrics.",
    )
    parser.add_argument(
        "--name",
        required=True,
        metavar="EXTENSION_NAME",
        help="Extension name as shown on the Hub (e.g. 'Meraki Extension', 'microsoft 365')",
    )
    parser.add_argument(
        "--reconfigure",
        action="store_true",
        help="Re-enter OAuth credentials even if already stored.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: create Auto-Adaptive/Above detectors for all metrics.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON payloads that would be sent, without making API calls.",
    )
    parser.add_argument(
        "--env-id",
        metavar="ENV_ID",
        help=(
            "Dynatrace environment ID (e.g. 'abc12345'). "
            "Constructs https://<env-id>.live.dynatrace.com and overrides the "
            "stored environmentUrl for this run."
        ),
    )
    parser.add_argument(
        "--scopes",
        metavar="SCOPES",
        default=None,
        help=(
            "Space-separated OAuth scopes to request, overriding the default "
            "(settings:schemas:read settings:objects:read settings:objects:write "
            "environment-api:extensions:read storage:metrics:read). "
            "Only add scopes your OAuth client was actually granted."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    env_url_hint = ""
    if args.env_id:
        from .config import env_id_to_url
        env_url_hint = f"\nEnvironment: [dim]{env_id_to_url(args.env_id)}[/dim]"

    console.print(Panel(
        f"[bold]Dynatrace Extension Alert Config[/bold]\n"
        f"Extension: [cyan]{args.name}[/cyan]{env_url_hint}",
        border_style="blue",
    ))

    # ── 1. Credentials ─────────────────────────────────────────────────────
    try:
        creds = get_or_prompt_credentials(reconfigure=args.reconfigure, env_id=args.env_id)
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted.[/yellow]")
        sys.exit(0)

    # ── 2. Authenticate ────────────────────────────────────────────────────
    console.print("Authenticating with Dynatrace…")
    try:
        from .auth import REQUIRED_SCOPES, get_token_with_fallback
        token, has_ext_scope = get_token_with_fallback(creds, scopes=args.scopes or REQUIRED_SCOPES)
    except AuthError as exc:
        console.print(f"[red]Authentication failed:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Unexpected auth error:[/red] {exc}")
        sys.exit(1)

    if not has_ext_scope:
        console.print(
            "[yellow]Note: token was issued without the extensions read scope "
            "(environment-api:extensions:read). Extension discovery via the "
            "environment API will likely fail. Grant that scope to your OAuth "
            "client for full functionality.[/yellow]"
        )

    client = DynatraceClient(env_url=creds["environmentUrl"], token=token)

    # ── 3. Connectivity check ───────────────────────────────────────────────
    try:
        client.get_schema("builtin:davis.anomaly-detectors")
        console.print("[green]Connected to Dynatrace environment.[/green]")
    except Exception as exc:
        console.print(f"[red]Cannot reach environment API:[/red] {exc}")
        sys.exit(1)

    # ── 4. Resolve extension ────────────────────────────────────────────────
    try:
        info = resolve_extension(args.name, client)
    except ExtensionNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if not info.feature_sets:
        console.print("[yellow]No feature sets / metrics found for this extension.[/yellow]")
        sys.exit(0)

    # ── 5. Interactive or auto selection ────────────────────────────────────
    try:
        if args.yes:
            choices = run_auto_flow(info)
        else:
            choices = run_interactive_flow(info)
    except KeyboardInterrupt:
        console.print("\n[yellow]Aborted.[/yellow]")
        sys.exit(0)

    if not choices:
        sys.exit(0)

    # ── 6. Build payloads ───────────────────────────────────────────────────
    payloads = build_all_payloads(choices, extension_name=args.name)

    if args.dry_run:
        console.print("\n[bold yellow]--- DRY RUN: no changes will be made ---[/bold yellow]\n")
        for p in payloads:
            console.print_json(json.dumps(p))
        sys.exit(0)

    # ── 7. POST to Settings API ─────────────────────────────────────────────
    console.print(f"\nCreating [bold]{len(payloads)}[/bold] anomaly detector(s)…")

    results_table = Table(show_lines=True)
    results_table.add_column("Metric Key", style="cyan")
    results_table.add_column("Model", style="white")
    results_table.add_column("Status", style="white")
    results_table.add_column("Object ID / Error", style="dim white")

    for choice, payload in zip(choices, payloads):
        try:
            obj_id = client.create_settings_object(payload)
            results_table.add_row(
                choice.metric.key,
                choice.model,
                "[green]Created[/green]",
                obj_id or "—",
            )
        except Exception as exc:
            results_table.add_row(
                choice.metric.key,
                choice.model,
                "[red]Failed[/red]",
                str(exc)[:80],
            )

    console.print(results_table)


if __name__ == "__main__":
    main()
