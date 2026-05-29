import pytest

from dynatrace_extension_alert_config.anomaly import build_payload, build_all_payloads
from dynatrace_extension_alert_config.models import DetectorChoice, Metric


@pytest.fixture
def sample_metric():
    return Metric(key="meraki.device.cpu_usage", name="Meraki Appliance CPU Usage", description="CPU Usage", feature_set="device-cpu")


def test_auto_adaptive_payload(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    payload = build_payload(choice, extension_name="Meraki")
    assert payload["schemaId"] == "builtin:anomaly-detection.metric-events"
    assert payload["scope"] == "environment"
    v = payload["value"]
    assert v["enabled"] is True
    assert v["queryDefinition"]["metricKey"] == "meraki.device.cpu_usage"
    assert v["queryDefinition"]["type"] == "METRIC_KEY"
    mp = v["modelProperties"]
    assert mp["type"] == "AUTO_ADAPTIVE_BASELINE"
    assert mp["alertCondition"] == "ABOVE"
    assert "numberOfSignalFluctuations" in mp
    assert mp["violatingSamples"] == 3
    assert mp["slidingWindow"] == 5
    assert mp["dealertingSamples"] == 5


def test_seasonal_payload(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="SEASONAL_BASELINE", direction="BELOW")
    payload = build_payload(choice, extension_name="Meraki")
    mp = payload["value"]["modelProperties"]
    assert mp["type"] == "SEASONAL_BASELINE"
    assert mp["alertCondition"] == "BELOW"


def test_static_threshold_payload(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD", direction="ABOVE", threshold=80.0)
    payload = build_payload(choice, extension_name="Meraki")
    mp = payload["value"]["modelProperties"]
    assert mp["type"] == "STATIC_THRESHOLD"
    assert mp["threshold"] == 80.0
    assert mp["unit"] == "NONE"
    assert mp["alertCondition"] == "ABOVE"


def test_static_threshold_requires_value(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD", direction="ABOVE", threshold=None)
    with pytest.raises(ValueError, match="threshold"):
        build_payload(choice, extension_name="Meraki")


def test_unknown_model_raises(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="UNKNOWN_MODEL", direction="ABOVE")
    with pytest.raises(ValueError, match="Unknown model"):
        build_payload(choice, extension_name="Meraki")


def test_summary_contains_metric_key(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    payload = build_payload(choice, extension_name="Meraki")
    assert "meraki.device.cpu_usage" in payload["value"]["summary"]


def test_build_all_payloads(sample_metric):
    choices = [
        DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE"),
        DetectorChoice(metric=sample_metric, model="STATIC_THRESHOLD", direction="BELOW", threshold=50.0),
    ]
    payloads = build_all_payloads(choices, extension_name="Meraki")
    assert len(payloads) == 2
    assert payloads[0]["value"]["modelProperties"]["type"] == "AUTO_ADAPTIVE_BASELINE"
    assert payloads[1]["value"]["modelProperties"]["type"] == "STATIC_THRESHOLD"


def test_event_template_fields(sample_metric):
    choice = DetectorChoice(metric=sample_metric, model="AUTO_ADAPTIVE_BASELINE", direction="ABOVE")
    payload = build_payload(choice, extension_name="Meraki")
    et = payload["value"]["eventTemplate"]
    assert et["eventType"] == "CUSTOM_ALERT"
    assert et["davisMerge"] is True
    assert "anomaly" in et["title"].lower()
