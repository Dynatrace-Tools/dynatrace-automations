from pathlib import Path

import pytest

from dynatrace_extension_alert_config.docs_scraper import parse_feature_sets, slugify

FIXTURE = Path(__file__).parent / "fixtures" / "meraki_docs.html"


@pytest.fixture
def meraki_html():
    return FIXTURE.read_text()


def test_slugify_simple():
    assert slugify("meraki") == "meraki"


def test_slugify_strips_extension_word():
    assert slugify("Meraki Extension") == "meraki"
    assert slugify("meraki extension") == "meraki"


def test_slugify_microsoft_365():
    assert slugify("Microsoft 365, Office 365") == "microsoft-365-office-365"


def test_slugify_leading_extension():
    assert slugify("Extension Meraki") == "meraki"


def test_parse_feature_sets_count(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    fs_names = [fs.name for fs in info.feature_sets]
    expected_fs = [
        "switchport-clients", "device-cpu", "self-monitoring", "device-uptime",
        "device-memory", "default", "device-status", "device-powersupply",
        "device-uplink", "device-uplink-usage",
    ]
    for expected in expected_fs:
        assert expected in fs_names, f"Missing feature set: {expected}"


def test_parse_switchport_clients(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    fs = next(fs for fs in info.feature_sets if fs.name == "switchport-clients")
    assert len(fs.metrics) == 1
    assert fs.metrics[0].key == "meraki.switchport.clients"
    assert fs.metrics[0].name == "Meraki SwitchPort Clients"


def test_parse_self_monitoring_has_four_metrics(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    fs = next(fs for fs in info.feature_sets if fs.name == "self-monitoring")
    keys = [m.key for m in fs.metrics]
    assert "meraki.api.connectivity" in keys
    assert "meraki.monitoring.organizations" in keys
    assert "meraki.monitoring.networks" in keys
    assert "meraki.monitoring.devices" in keys


def test_parse_default_feature_set(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    fs = next(fs for fs in info.feature_sets if fs.name == "default")
    keys = [m.key for m in fs.metrics]
    assert "com.dynatrace.extension.network_device.sysuptime" in keys
    assert len(keys) == 9


def test_parse_device_memory(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    fs = next(fs for fs in info.feature_sets if fs.name == "device-memory")
    assert len(fs.metrics) == 4
    keys = {m.key for m in fs.metrics}
    assert keys == {
        "meraki.device.memory_used",
        "meraki.device.memory_free",
        "meraki.device.memory_total",
        "meraki.device.memory_usage",
    }


def test_all_metrics_total(meraki_html):
    info = parse_feature_sets(meraki_html, extension_name="meraki")
    total = sum(len(fs.metrics) for fs in info.feature_sets)
    # 1+1+4+1+4+9+1+1+2+2 = 26
    assert total == 26
