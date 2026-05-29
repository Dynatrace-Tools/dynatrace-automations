from __future__ import annotations

from .models import DetectorChoice


def build_payload(choice: DetectorChoice, extension_name: str) -> dict:
    """Build a single builtin:anomaly-detection.metric-events settings object."""
    metric = choice.metric
    summary = f"{extension_name} – {metric.key} anomaly detection"

    # Title uses the metric description when available, falling back to the
    # display name and finally the metric key. {alert_condition} and {threshold}
    # are Dynatrace event-template placeholders resolved at event time (for
    # baseline models {threshold} resolves to the computed baseline value).
    subject = metric.description or metric.name or metric.key
    title = f"{subject} is {{alert_condition}} the threshold of {{threshold}}"

    model_props = _build_model_properties(choice)

    return {
        "schemaId": "builtin:anomaly-detection.metric-events",
        "scope": "environment",
        "value": {
            "enabled": True,
            "summary": summary,
            "queryDefinition": {
                "type": "METRIC_KEY",
                "metricKey": metric.key,
                "aggregation": "AVG",
                "dimensionFilter": [],
            },
            "modelProperties": model_props,
            "eventTemplate": {
                "title": title,
                "description": (
                    f"The metric {metric.key} is {{alert_condition}} "
                    f"the threshold of {{threshold}}."
                ),
                "eventType": "CUSTOM_ALERT",
                "davisMerge": True,
                "metadata": [],
            },
            "eventEntityDimensionKey": None,
        },
    }


def _build_model_properties(choice: DetectorChoice) -> dict:
    base = {
        "alertCondition": choice.direction,
        "alertingOnMissingData": False,
        "violatingSamples": 3,
        "slidingWindow": 5,
        "dealertingSamples": 5,
    }

    if choice.model == "AUTO_ADAPTIVE_BASELINE":
        return {
            "type": "AUTO_ADAPTIVE_BASELINE",
            "numberOfSignalFluctuations": 1.0,
            **base,
        }
    elif choice.model == "SEASONAL_BASELINE":
        return {
            "type": "SEASONAL_BASELINE",
            "numberOfSignalFluctuations": 1.0,
            **base,
        }
    elif choice.model == "STATIC_THRESHOLD":
        if choice.threshold is None:
            raise ValueError("Static threshold requires a numeric threshold value.")
        return {
            "type": "STATIC_THRESHOLD",
            "threshold": choice.threshold,
            "unit": "NONE",
            **base,
        }
    else:
        raise ValueError(f"Unknown model type: {choice.model}")


def build_all_payloads(choices: list[DetectorChoice], extension_name: str) -> list[dict]:
    return [build_payload(c, extension_name) for c in choices]
