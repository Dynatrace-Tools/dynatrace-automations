from __future__ import annotations

from .models import DetectorChoice


def build_payload(choice: DetectorChoice, extension_name: str) -> dict:
    """Build a single builtin:anomaly-detection.metric-events settings object."""
    metric = choice.metric
    summary = f"{extension_name} – {metric.key} anomaly detection"
    title = metric.name if metric.name and metric.name != metric.key else metric.key

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
                "entityFilter": {
                    "dimensionKey": "dt.entity.host",
                    "conditions": [],
                },
                "dimensionFilter": [],
            },
            "modelProperties": model_props,
            "eventTemplate": {
                "title": f"{title} anomaly",
                "description": (
                    f"The metric {metric.key} triggered an anomaly event. "
                    "Davis detected that the value went {alert_condition}."
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
