import pytest

from dynatrace_extension_alert_config.anomaly import (
    SCHEMA_ID,
    build_all_payloads,
    build_dql_query,
    build_event_title,
    build_payload,
)
from dynatrace_extension_alert_config.models import DetectorChoice, Metric


@pytest.fixture
def sample_metric():
    return Metric(
        key="meraki.device.cpu_usage",
        name="Meraki Appliance CPU Usage",
        description="CPU Usage",
        feature_set="device-cpu",
        dimensions=["device.name", "device.serial"],
    )


def _input_map(payload):
    fields = payload["value"]["analyzer"]["input"]
    return {f["key"]: f["value"] for f in fields}


def _event_props(payload):
    props = payload["value"]["eventTemplate"]["properties"]
    return {p["key"]: p["value"] for p in props}


# ── DQL query builder ───────────────────────────────────────────────────────

def test_dql_no_split():
    q = build_dql_query("meraki.device.cpu_usage", [])
    assert q == (
        "timeseries { avg(meraki.device.cpu_usage), "
        "value.A = avg(meraki.device.cpu_usage, scalar: true) }, interval: 1m"
    )


def test_dql_single_split():
    q = build_dql_query("meraki.device.cpu_usage", ["device.name"])
    assert ", by: { device.name }" in q
    assert q.endswith(", interval: 1m")


def test_dql_multi_split():
    q = build_dql_query("m.key", ["a", "b"])
    assert ", by: { a, b }" in q


# ── Event title ─────────────────────────────────────────────────────────────

def test_event_title_with_split():
    t = build_event_title("Meraki", "CPU Usage", ["device.name"])
    assert t == "Meraki - CPU Usage on {dims:device.name} is {alert_condition} the threshold of {threshold}"


def test_event_title_multi_split():
    t = build_event_title("Meraki", "CPU", ["a", "b"])
    assert "on {dims:a}, {dims:b} is" in t


def test_event_title_no_split_omits_on_clause():
    t = build_event_title("Meraki", "CPU Usage", [])
    assert t == "Meraki - CPU Usage is {alert_condition} the threshold of {threshold}"
    assert " on " not in t


# ── Payload ─────────────────────────────────────────────────────────────────

def test_payload_schema_and_title(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE",
                            direction="ABOVE", split_dimensions=["device.name"])
    p = build_payload(choice, "Meraki")
    assert p["schemaId"] == SCHEMA_ID
    assert p["scope"] == "environment"
    assert p["value"]["title"] == "Meraki - Meraki Appliance CPU Usage"
    assert p["value"]["enabled"] is True
    assert p["value"]["source"] == "dynatrace-extension-alert-config"


def test_payload_analyzer_name_auto(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    p = build_payload(choice, "Meraki")
    assert p["value"]["analyzer"]["name"].endswith("AutoAdaptiveAnomalyDetectionAnalyzer")


def test_payload_analyzer_name_seasonal(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="SEASONAL_BASELINE", direction="BELOW")
    p = build_payload(choice, "Meraki")
    assert p["value"]["analyzer"]["name"].endswith("SeasonalBaselineAnomalyDetectionAnalyzer")


def test_payload_static_includes_threshold(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD",
                            direction="ABOVE", threshold=80.0)
    p = build_payload(choice, "Meraki")
    assert p["value"]["analyzer"]["name"].endswith("StaticThresholdAnomalyDetectionAnalyzer")
    im = _input_map(p)
    assert im["threshold"] == "80"          # integer rendered without .0
    assert im["alertCondition"] == "ABOVE"
    assert im["violatingSamples"] == "3"
    assert im["slidingWindow"] == "5"
    assert im["dealertingSamples"] == "5"
    assert "interval: 1m" in im["query"]


def test_payload_static_decimal_threshold(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD",
                            direction="BELOW", threshold=1.5)
    p = build_payload(choice, "Meraki")
    assert _input_map(p)["threshold"] == "1.5"


def test_payload_baseline_has_no_threshold(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    p = build_payload(choice, "Meraki")
    assert "threshold" not in _input_map(p)


def test_payload_static_requires_threshold(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD", direction="ABOVE", threshold=None)
    with pytest.raises(ValueError, match="threshold"):
        build_payload(choice, "Meraki")


def test_payload_unknown_model(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="NOPE", direction="ABOVE")
    with pytest.raises(ValueError, match="Unknown model"):
        build_payload(choice, "Meraki")


def test_payload_query_uses_split_dims(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE",
                            direction="ABOVE", split_dimensions=["device.name"])
    p = build_payload(choice, "Meraki")
    assert "by: { device.name }" in _input_map(p)["query"]
    assert _event_props(p)["event.name"] == (
        "Meraki - Meraki Appliance CPU Usage on {dims:device.name} "
        "is {alert_condition} the threshold of {threshold}"
    )


def test_event_template_uses_properties(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    et = build_payload(choice, "Meraki")["value"]["eventTemplate"]
    # davis.anomaly-detectors uses a properties set, not title/description/eventType
    assert "title" not in et
    assert "properties" in et
    props = _event_props(build_payload(choice, "Meraki"))
    assert "event.name" in props
    assert "event.description" in props


def test_analyzer_input_is_a_list(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    p = build_payload(choice, "Meraki")
    assert isinstance(p["value"]["analyzer"]["input"], list)


def test_execution_settings_present(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    p = build_payload(choice, "Meraki")
    # queryOffset must be within the schema's allowed 1-60 range
    assert p["value"]["executionSettings"]["queryOffset"] == 1


def test_query_offset_override(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    p = build_payload(choice, "Meraki", query_offset=15)
    assert p["value"]["executionSettings"]["queryOffset"] == 15


def test_build_all_payloads(sample_metric):
    choices = [
        DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE"),
        DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD", direction="BELOW", threshold=50.0),
    ]
    payloads = build_all_payloads(choices, "Meraki")
    assert len(payloads) == 2
    assert all(p["schemaId"] == SCHEMA_ID for p in payloads)
