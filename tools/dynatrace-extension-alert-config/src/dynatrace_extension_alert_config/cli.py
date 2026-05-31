from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .anomaly import (
    SCHEMA_ID,
    build_all_payloads,
    classify_against_existing,
    config_title,
    is_tool_created,
)
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
    parser.add_argument(
        "--query-offset",
        type=int,
        default=1,
        metavar="MINUTES",
        help="Query offset in minutes (1-60) for the detector's sliding window. "
             "Required by the schema; defaults to 1.",
    )
    parser.add_argument(
        "--dump-schema",
        action="store_true",
        help="Print the live builtin:davis.anomaly-detectors schema JSON and exit "
             "(useful for verifying the exact payload structure).",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Delete the anomaly detectors this tool created for --name "
             "(matched by source tag + the '<Extension> - ' title prefix). "
             "Prompts for confirmation unless --yes is given.",
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
        from .auth import REQUIRED_SCOPES, get_bearer_token, get_token_with_fallback
        _, has_ext_scope, effective_scopes = get_token_with_fallback(
            creds, scopes=args.scopes or REQUIRED_SCOPES
        )
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

    # Provide a refreshing token: the interactive flow can outlast a token's
    # 5-minute lifetime, so the client fetches a fresh (cached) token per request.
    def token_provider() -> str:
        return get_bearer_token(creds, effective_scopes)

    client = DynatraceClient(env_url=creds["environmentUrl"], token_provider=token_provider)

    # ── 3. Connectivity check ───────────────────────────────────────────────
    try:
        schema = client.get_schema("builtin:davis.anomaly-detectors")
        console.print("[green]Connected to Dynatrace environment.[/green]")
    except Exception as exc:
        console.print(f"[red]Cannot reach environment API:[/red] {exc}")
        sys.exit(1)

    if args.dump_schema:
        console.print_json(json.dumps(schema))
        sys.exit(0)

    # ── Undo: delete tool-created detectors for this extension ───────────────
    if args.undo:
        _run_undo(client, args.name, assume_yes=args.yes)
        return

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
    if not 1 <= args.query_offset <= 60:
        console.print("[red]--query-offset must be between 1 and 60.[/red]")
        sys.exit(1)
    payloads = build_all_payloads(choices, extension_name=args.name, query_offset=args.query_offset)

    # Idempotency: fetch what already exists so we never create duplicates.
    try:
        existing_values = [
            item.get("value", {}) for item in client.list_settings_objects(SCHEMA_ID)
        ]
    except Exception as exc:
        console.print(f"[yellow]Could not read existing detectors (idempotency "
                      f"check skipped): {exc}[/yellow]")
        existing_values = []

    if args.dry_run:
        console.print("\n[bold yellow]--- DRY RUN: no changes will be made ---[/bold yellow]\n")
        for choice, p in zip(choices, payloads):
            status = classify_against_existing(p["value"], existing_values)
            label = {
                "new": "[green]would CREATE[/green]",
                "identical": "[dim]already exists — would SKIP[/dim]",
                "conflict": "[yellow]exists with different settings — would SKIP[/yellow]",
            }[status]
            console.print(f"{label}  [cyan]{choice.metric.key}[/cyan]")
            console.print_json(json.dumps(p))
        sys.exit(0)

    # ── 7. POST to Settings API (idempotent) ─────────────────────────────────
    console.print(f"\nProcessing [bold]{len(payloads)}[/bold] detector(s)…")

    results_table = Table(show_lines=True)
    results_table.add_column("Metric Key", style="cyan")
    results_table.add_column("Model", style="white")
    results_table.add_column("Status", style="white")
    results_table.add_column("Object ID / Note", style="dim white")

    failures: list[tuple[str, str]] = []
    created = skipped = conflicts = 0
    for choice, payload in zip(choices, payloads):
        status = classify_against_existing(payload["value"], existing_values)
        if status == "identical":
            skipped += 1
            results_table.add_row(choice.metric.key, choice.model,
                                  "[dim]Exists[/dim]", "identical — skipped")
            continue
        if status == "conflict":
            conflicts += 1
            results_table.add_row(choice.metric.key, choice.model,
                                  "[yellow]Exists[/yellow]", "differs — skipped (see note)")
            continue
        try:
            obj_id = client.create_settings_object(payload)
            created += 1
            results_table.add_row(choice.metric.key, choice.model,
                                  "[green]Created[/green]", obj_id or "—")
        except Exception as exc:
            results_table.add_row(choice.metric.key, choice.model, "[red]Failed[/red]", "—")
            failures.append((choice.metric.key, str(exc)))

    console.print(results_table)
    console.print(
        f"\n[bold]Summary:[/bold] [green]{created} created[/green], "
        f"[dim]{skipped} already existed[/dim], "
        f"[yellow]{conflicts} differ[/yellow], [red]{len(failures)} failed[/red]."
    )

    if conflicts:
        console.print(
            "\n[yellow]Some detectors already exist with different settings "
            "(e.g. a changed threshold). They were left untouched. To replace "
            f"them, run:[/yellow]\n  [cyan]dynatrace-extension-alert-config "
            f'--name "{args.name}" --env-id <env> --undo[/cyan]  then re-run.'
        )

    if failures:
        console.print("\n[red bold]Errors:[/red bold]")
        for key, msg in failures:
            console.print(f"[red]• {key}[/red]\n  {msg}\n")


def _run_undo(client: DynatraceClient, extension_name: str, assume_yes: bool = False) -> None:
    """Delete the detectors this tool created for the given extension name."""
    try:
        items = client.list_settings_objects(SCHEMA_ID)
    except Exception as exc:
        console.print(f"[red]Could not list existing detectors:[/red] {exc}")
        sys.exit(1)

    prefix = f"{extension_name} - "
    targets = [
        it for it in items
        if is_tool_created(it.get("value", {}))
        and config_title(it.get("value", {})).startswith(prefix)
    ]

    if not targets:
        console.print(
            f"[yellow]Nothing to undo — no tool-created detectors found for "
            f"'{extension_name}'.[/yellow]"
        )
        return

    table = Table(title=f"Detectors to delete for '{extension_name}'", show_lines=False)
    table.add_column("Title", style="cyan")
    table.add_column("Object ID", style="dim white")
    for it in targets:
        table.add_row(config_title(it.get("value", {})), it.get("objectId", "—"))
    console.print(table)

    if not assume_yes:
        import questionary
        confirmed = questionary.confirm(
            f"Delete these {len(targets)} detector(s)? This cannot be undone.",
            default=False,
        ).ask()
        if not confirmed:
            console.print("[yellow]Aborted. Nothing deleted.[/yellow]")
            return

    deleted = 0
    failures: list[tuple[str, str]] = []
    for it in targets:
        obj_id = it.get("objectId", "")
        try:
            client.delete_settings_object(obj_id)
            deleted += 1
        except Exception as exc:
            failures.append((config_title(it.get("value", {})), str(exc)))

    console.print(f"\n[bold]Deleted {deleted} of {len(targets)} detector(s).[/bold]")
    if failures:
        console.print("\n[red bold]Errors:[/red bold]")
        for title, msg in failures:
            console.print(f"[red]• {title}[/red]\n  {msg}\n")


if __name__ == "__main__":
    main()
