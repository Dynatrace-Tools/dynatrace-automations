from __future__ import annotations
import re
from typing import Optional

from .client import DynatraceClient
from .docs_scraper import scrape_extension
from .models import ExtensionInfo, FeatureSet, Metric


def _normalize_name(name: str) -> str:
    """Lower-case, strip trailing/leading 'extension', collapse whitespace."""
    n = name.lower()
    n = re.sub(r"\bextension\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _fuzzy_match(needle: str, candidates: list[str]) -> Optional[str]:
    """Return best-match candidate for a normalized display name."""
    needle_norm = _normalize_name(needle)
    for c in candidates:
        # candidates are like com.dynatrace.extension.meraki
        tail = c.split(".")[-1].replace("-", " ").replace("_", " ")
        if needle_norm in tail or tail in needle_norm:
            return c
    # Looser: any word from needle appears in the candidate
    needle_words = set(needle_norm.split())
    for c in candidates:
        tail_words = set(re.split(r"[\.\-_]", c))
        if needle_words & tail_words:
            return c
    return None


def _parse_extension_yaml(schema_data: dict, ext_display_name: str) -> ExtensionInfo:
    """
    Extract feature sets and metrics from the extension schema response.
    The /api/v2/extensions/{name}/{version} endpoint returns the full extension schema
    including metrics grouped by feature set.
    """
    version = schema_data.get("version", "unknown")
    metrics_raw = schema_data.get("metrics", [])

    # Build feature_set -> [Metric] map
    fs_map: dict[str, list[Metric]] = {}

    for m in metrics_raw:
        key = m.get("key", "")
        if not key:
            continue

        # Resolve feature set with inheritance: metric > subgroup > group > "default"
        feature_set = (
            m.get("featureSet")
            or m.get("subgroupFeatureSet")
            or m.get("groupFeatureSet")
            or "default"
        )

        display_name = (
            m.get("metadata", {}).get("displayName")
            or m.get("displayName")
            or key
        )
        description = (
            m.get("metadata", {}).get("description")
            or m.get("description")
            or ""
        )

        metric = Metric(
            key=key,
            name=display_name,
            description=description,
            feature_set=feature_set,
        )
        fs_map.setdefault(feature_set, []).append(metric)

    feature_sets = [FeatureSet(name=fs_name, metrics=ms) for fs_name, ms in fs_map.items()]
    return ExtensionInfo(name=ext_display_name, version=version, feature_sets=feature_sets)


def resolve_extension(name: str, client: DynatraceClient) -> ExtensionInfo:
    """Resolve an extension by display name, using env API first then docs fallback."""
    from rich.console import Console
    console = Console()

    # --- Primary: environment Extensions 2.0 API ---
    try:
        installed = client.list_extensions()
        ext_names = [e.get("extensionName", "") for e in installed]
        matched = _fuzzy_match(name, ext_names)

        if matched:
            # Get the active version from environment configuration
            try:
                env_cfg = client.get_extension_environment_config(matched)
                version = env_cfg.get("version", "")
            except Exception:
                version = ""

            if not version:
                # Fall back to the latest installed version
                for e in installed:
                    if e.get("extensionName") == matched:
                        version = e.get("version", "")
                        break

            if version:
                console.print(
                    f"[green]Found extension[/green] [bold]{matched}[/bold] "
                    f"version [bold]{version}[/bold] (via environment API)"
                )
                schema_data = client.get_extension_schema(matched, version)
                info = _parse_extension_yaml(schema_data, ext_display_name=name)
                if info.feature_sets:
                    return info
    except Exception as exc:
        console.print(f"[yellow]Environment API lookup failed:[/yellow] {exc}")

    # --- Fallback: docs scraping ---
    console.print("[yellow]Falling back to Dynatrace docs scraping…[/yellow]")
    info = scrape_extension(name)
    if info and info.feature_sets:
        return info

    raise ExtensionNotFoundError(
        f"Could not resolve extension '{name}' from the environment API or the docs. "
        "Check the extension name and ensure it is installed in your environment."
    )


class ExtensionNotFoundError(Exception):
    pass
