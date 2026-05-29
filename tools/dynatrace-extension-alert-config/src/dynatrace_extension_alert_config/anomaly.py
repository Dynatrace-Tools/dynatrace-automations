from __future__ import annotations

from .models import DetectorChoice

SCHEMA_ID = "builtin:davis.anomaly-detectors"
SOURCE = "dynatrace-extension-alert-config"

_ANALYZER_PREFIX = "dt.statistics.ui.anomaly_detection"
_ANALYZER_NAMES = {
    "AUTO_ADAPTIVE_BASELINE": f"{_ANALYZER_PREFIX}.AutoAdaptiveAnomalyDetectionAnalyzer",
    "SEASONAL_BASELINE": f"{_ANALYZER_PREFIX}.SeasonalBaselineAnomalyDetectionAnalyzer",
    "STATIC_THRESHOLD": f"{_ANALYZER_PREFIX}.StaticThresholdAnomalyDetectionAnalyzer",
}


def build_dql_query(metric_key: str, split_dimensions: list[str]) -> str:
    """Build the DQL timeseries query the Davis detector evaluates.

    timeseries { avg(<key>), value.A = avg(<key>, scalar: true) }, by: { d1, d2 }, interval: 1m

    The ``value.A`` scalar measure is the field the analyzer evaluates; the
    plain ``avg`` measure provides the charted series. ``interval: 1m`` is
    mandatory for Davis anomaly detectors.
    """
    query = (
        f"timeseries {{ avg({metric_key}), "
        f"value.A = avg({metric_key}, scalar: true) }}"
    )
    if split_dimensions:
        query += f", by: {{ {', '.join(split_dimensions)} }}"
    query += ", interval: 1m"
    return query


def build_event_title(extension_name: str, metric_name: str, split_dimensions: list[str]) -> str:
    """<Ext> - <Metric Name> on {dims:d1}, {dims:d2} is {alert_condition} the threshold of {threshold}

    The ``on …`` clause is omitted when there is no split dimension.
    """
    base = f"{extension_name} - {metric_name}"
    if split_dimensions:
        dims = ", ".join(f"{{dims:{d}}}" for d in split_dimensions)
        base += f" on {dims}"
    return f"{base} is {{alert_condition}} the threshold of {{threshold}}"


def _config_title(extension_name: str, metric_name: str) -> str:
    return f"{extension_name} - {metric_name}"


def _analyzer_input(choice: DetectorChoice, query: str) -> list[dict]:
    """The analyzer_input_field list. All values are strings, per the schema."""
    fields = [
        {"key": "query", "value": query},
        {"key": "alertCondition", "value": choice.direction},
        {"key": "alertOnMissingData", "value": "false"},
        {"key": "violatingSamples", "value": "3"},
        {"key": "slidingWindow", "value": "5"},
        {"key": "dealertingSamples", "value": "5"},
    ]
    if choice.model == "STATIC_THRESHOLD":
        if choice.threshold is None:
            raise ValueError("Static threshold requires a numeric threshold value.")
        # Render integers without a trailing .0
        threshold = choice.threshold
        value = str(int(threshold)) if float(threshold).is_integer() else str(threshold)
        fields.append({"key": "threshold", "value": value})
    return fields


def build_payload(choice: DetectorChoice, extension_name: str) -> dict:
    """Build a single builtin:davis.anomaly-detectors settings object."""
    metric = choice.metric
    metric_name = metric.name or metric.key
    analyzer_name = _ANALYZER_NAMES.get(choice.model)
    if analyzer_name is None:
        raise ValueError(f"Unknown model type: {choice.model}")

    query = build_dql_query(metric.key, choice.split_dimensions)

    return {
        "schemaId": SCHEMA_ID,
        "scope": "environment",
        "value": {
            "enabled": True,
            "title": _config_title(extension_name, metric_name),
            "description": f"Auto-created for {extension_name} metric {metric.key}",
            "source": SOURCE,
            "analyzer": {
                "name": analyzer_name,
                "input": {"analyzer_input_field": _analyzer_input(choice, query)},
            },
            # builtin:davis.anomaly-detectors event template — note this schema
            # does NOT use the metric-events `eventType` field.
            "eventTemplate": {
                "title": build_event_title(extension_name, metric_name, choice.split_dimensions),
                "description": (
                    f"The metric {metric.key} is {{alert_condition}} "
                    f"the threshold of {{threshold}}."
                ),
                "davisMerge": True,
                "metadata": [],
            },
        },
    }


def build_all_payloads(choices: list[DetectorChoice], extension_name: str) -> list[dict]:
    return [build_payload(c, extension_name) for c in choices]
