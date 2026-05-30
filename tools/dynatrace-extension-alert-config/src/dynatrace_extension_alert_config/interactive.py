from __future__ import annotations
from typing import Optional

import questionary
from rich.console import Console
from rich.table import Table

from .models import DetectorChoice, ExtensionInfo, Metric
from .recommendations import format_number, recommend_threshold

console = Console()

MODEL_CHOICES = [
    questionary.Choice("Auto-Adaptive Baseline", value="AUTO_ADAPTIVE_BASELINE"),
    questionary.Choice("Seasonal Baseline", value="SEASONAL_BASELINE"),
    questionary.Choice("Static Threshold", value="STATIC_THRESHOLD"),
]

DIRECTION_CHOICES = [
    questionary.Choice("Above threshold", value="ABOVE"),
    questionary.Choice("Below threshold", value="BELOW"),
]


def _display_extension_summary(info: ExtensionInfo) -> None:
    table = Table(title=f"Extension: {info.name}  (v{info.version})", show_lines=True)
    table.add_column("Feature Set", style="cyan")
    table.add_column("Metric Key", style="white")
    table.add_column("Metric Name", style="dim white")
    table.add_column("Unit", style="dim white")
    table.add_column("Dimensions", style="dim white")
    for fs in info.feature_sets:
        for m in fs.metrics:
            table.add_row(fs.name, m.key, m.name, m.unit or "—", ", ".join(m.dimensions) or "—")
    console.print(table)


def select_metrics(info: ExtensionInfo) -> list[Metric]:
    """Show a checkbox list of all metrics grouped by feature set."""
    _display_extension_summary(info)

    choices = []
    for fs in info.feature_sets:
        choices.append(questionary.Separator(f"── {fs.name} ──"))
        for m in fs.metrics:
            label = f"{m.key}"
            if m.name and m.name != m.key:
                label += f"  ({m.name})"
            choices.append(questionary.Choice(label, value=m))

    selected = questionary.checkbox(
        "Select metrics to create Davis Anomaly Detection for (Space to toggle, Enter to confirm):",
        choices=choices,
    ).ask()

    if selected is None:
        raise KeyboardInterrupt
    return selected


def configure_detector(metric: Metric) -> Optional[DetectorChoice]:
    """Interactively configure a single metric's detector settings."""
    # questionary prompts are plain text — render emphasis via rich separately.
    unit_suffix = f"  [unit: {metric.unit}]" if metric.unit else ""
    console.rule(f"[bold cyan]{metric.key}[/bold cyan]{unit_suffix}")

    model = questionary.select(
        f"Detection model for {metric.key}:",
        choices=MODEL_CHOICES,
    ).ask()
    if model is None:
        return None

    # Direction is asked before the threshold so we can recommend a value that
    # depends on it (e.g. above 80% vs. below 20% for a percentage metric).
    direction = questionary.select(
        "Alert when metric goes:",
        choices=DIRECTION_CHOICES,
    ).ask()
    if direction is None:
        return None

    threshold: Optional[float] = None
    if model == "STATIC_THRESHOLD":
        recommended = recommend_threshold(metric.unit, direction)
        prompt = "Static threshold value (numeric)"
        if metric.unit:
            prompt += f" [unit: {metric.unit}]"
        default = ""
        if recommended is not None:
            default = format_number(recommended)
            prompt += f" — recommended {default}"
        raw = questionary.text(
            prompt + ":",
            default=default,
            validate=lambda v: _validate_number(v),
        ).ask()
        if raw is None:
            return None
        threshold = float(raw)

    split_dimensions: list[str] = []
    if metric.dimensions:
        selected = questionary.checkbox(
            "Split by which dimension(s)? (Space to toggle, Enter to confirm; "
            "leave empty for no split)",
            choices=[questionary.Choice(d, value=d) for d in metric.dimensions],
        ).ask()
        if selected is None:
            return None
        split_dimensions = selected

    return DetectorChoice(
        metric=metric,
        model=model,
        direction=direction,
        threshold=threshold,
        split_dimensions=split_dimensions,
    )


def _validate_number(value: str) -> bool | str:
    try:
        float(value)
        return True
    except ValueError:
        return "Please enter a valid number."


def run_interactive_flow(info: ExtensionInfo) -> list[DetectorChoice]:
    """Full interactive selection: metric checkbox then per-metric config."""
    selected_metrics = select_metrics(info)
    if not selected_metrics:
        console.print("[yellow]No metrics selected. Nothing to do.[/yellow]")
        return []

    console.print(f"\n[bold]Configuring detectors for {len(selected_metrics)} metric(s)…[/bold]\n")
    choices: list[DetectorChoice] = []
    for m in selected_metrics:
        choice = configure_detector(m)
        if choice:
            choices.append(choice)
    return choices


def run_auto_flow(info: ExtensionInfo) -> list[DetectorChoice]:
    """Non-interactive: auto-adaptive baseline / above for all metrics."""
    choices = []
    for m in info.all_metrics():
        choices.append(DetectorChoice(
            metric=m,
            model="AUTO_ADAPTIVE_BASELINE",
            direction="ABOVE",
        ))
    return choices
