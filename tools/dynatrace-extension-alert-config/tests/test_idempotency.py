import pytest

from dynatrace_extension_alert_config.anomaly import (
    build_payload,
    classify_against_existing,
    config_signature,
    config_title,
    is_tool_created,
)
from dynatrace_extension_alert_config.models import DetectorChoice, Metric


@pytest.fixture
def payload():
    m = Metric(key="meraki.device.cpu_usage", name="CPU Usage", dimensions=["device.name"], unit="Percent")
    choice = DetectorChoice(metric=m, model="STATIC_THRESHOLD", direction="ABOVE", threshold=80.0)
    return build_payload(choice, "Meraki Extension")


def test_config_title(payload):
    assert config_title(payload["value"]) == "Meraki Extension - CPU Usage"


def test_identical_is_detected(payload):
    # The very same value already exists -> identical
    existing = [payload["value"]]
    assert classify_against_existing(payload["value"], existing) == "identical"


def test_new_when_nothing_exists(payload):
    assert classify_against_existing(payload["value"], []) == "new"


def test_new_when_different_metric(payload):
    other = Metric(key="meraki.device.memory_used", name="Memory Used")
    other_payload = build_payload(
        DetectorChoice(metric=other, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE"),
        "Meraki Extension",
    )
    assert classify_against_existing(payload["value"], [other_payload["value"]]) == "new"


def test_conflict_when_same_title_different_threshold(payload):
    # Same metric/title, but threshold changed from 80 -> 50 = conflict
    changed = build_payload(
        DetectorChoice(
            metric=Metric(key="meraki.device.cpu_usage", name="CPU Usage",
                          dimensions=["device.name"], unit="Percent"),
            model="STATIC_THRESHOLD", direction="ABOVE", threshold=50.0,
        ),
        "Meraki Extension",
    )
    assert classify_against_existing(payload["value"], [changed["value"]]) == "conflict"


def test_conflict_when_same_title_different_model(payload):
    changed = build_payload(
        DetectorChoice(
            metric=Metric(key="meraki.device.cpu_usage", name="CPU Usage",
                          dimensions=["device.name"], unit="Percent"),
            model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE",
        ),
        "Meraki Extension",
    )
    assert classify_against_existing(payload["value"], [changed["value"]]) == "conflict"


def test_signature_ignores_input_order(payload):
    # Reversing the analyzer input order must not change the signature.
    v1 = payload["value"]
    v2 = json_roundtrip(v1)
    v2["analyzer"]["input"] = list(reversed(v2["analyzer"]["input"]))
    assert config_signature(v1) == config_signature(v2)


def test_is_tool_created(payload):
    assert is_tool_created(payload["value"]) is True
    assert is_tool_created({"source": "something-else"}) is False
    assert is_tool_created({}) is False


def json_roundtrip(obj):
    import json
    return json.loads(json.dumps(obj))
