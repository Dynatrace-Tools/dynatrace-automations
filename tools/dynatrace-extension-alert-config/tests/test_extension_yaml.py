import io
import zipfile

from dynatrace_extension_alert_config.extension_yaml import (
    parse_extension_yaml,
    parse_extension_zip,
)

# A simplified extension.yaml exercising: top-level metric metadata, feature
# sets on groups (inherited by metrics), per-metric override, and a metric with
# no feature set (-> default).
SAMPLE_YAML = """
name: custom:com.dynatrace.extension.meraki
version: 2.3.1
metrics:
  - key: meraki.device.cpu_usage
    metadata:
      displayName: Meraki Appliance CPU Usage
      description: CPU Usage collected for the top MX devices
  - key: meraki.device.memory_used
    metadata:
      displayName: Meraki Device Memory Used
      description: Meraki Device Memory Used kB
  - key: meraki.api.connectivity
    metadata:
      displayName: Meraki API Connectivity
      description: Was Dynatrace able to poll the Meraki API
  - key: com.dynatrace.extension.network_device.sysuptime
    metadata: {}
python:
  runtime:
    module: meraki_extension
  activation: {}
snmp:
  group:
    - featureSet: device-cpu
      subgroups:
        - subgroup: cpu
          metrics:
            - key: meraki.device.cpu_usage
              value: oid:1.3.6.1
    - featureSet: device-memory
      subgroups:
        - subgroup: mem
          metrics:
            - key: meraki.device.memory_used
              value: oid:1.3.6.2
    - featureSet: self-monitoring
      subgroups:
        - subgroup: api
          metrics:
            - key: meraki.api.connectivity
              value: oid:1.3.6.3
"""


def test_parse_yaml_feature_sets():
    info = parse_extension_yaml(SAMPLE_YAML, ext_display_name="Meraki")
    fs_names = {fs.name for fs in info.feature_sets}
    assert "device-cpu" in fs_names
    assert "device-memory" in fs_names
    assert "self-monitoring" in fs_names
    # The metric with no feature set lands in default
    assert "default" in fs_names


def test_parse_yaml_metric_mapping():
    info = parse_extension_yaml(SAMPLE_YAML, ext_display_name="Meraki")
    fs = {f.name: f for f in info.feature_sets}
    cpu_keys = {m.key for m in fs["device-cpu"].metrics}
    assert cpu_keys == {"meraki.device.cpu_usage"}
    default_keys = {m.key for m in fs["default"].metrics}
    assert "com.dynatrace.extension.network_device.sysuptime" in default_keys


def test_parse_yaml_keeps_metadata():
    info = parse_extension_yaml(SAMPLE_YAML, ext_display_name="Meraki")
    cpu = next(m for fs in info.feature_sets for m in fs.metrics if m.key == "meraki.device.cpu_usage")
    assert cpu.name == "Meraki Appliance CPU Usage"
    assert "CPU Usage" in cpu.description


def test_parse_yaml_version():
    info = parse_extension_yaml(SAMPLE_YAML, ext_display_name="Meraki")
    assert info.version == "2.3.1"


def test_all_metrics_present():
    info = parse_extension_yaml(SAMPLE_YAML, ext_display_name="Meraki")
    keys = {m.key for fs in info.feature_sets for m in fs.metrics}
    assert keys == {
        "meraki.device.cpu_usage",
        "meraki.device.memory_used",
        "meraki.api.connectivity",
        "com.dynatrace.extension.network_device.sysuptime",
    }


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_parse_zip_flat():
    zip_bytes = _make_zip({"extension.yaml": SAMPLE_YAML.encode()})
    info = parse_extension_zip(zip_bytes, ext_display_name="Meraki")
    assert info is not None
    assert len(info.feature_sets) >= 3


def test_parse_zip_nested():
    inner = _make_zip({"extension.yaml": SAMPLE_YAML.encode()})
    outer = _make_zip({"extension.zip": inner, "extension.zip.sig": b"signature"})
    info = parse_extension_zip(outer, ext_display_name="Meraki")
    assert info is not None
    keys = {m.key for fs in info.feature_sets for m in fs.metrics}
    assert "meraki.device.cpu_usage" in keys


def test_parse_zip_no_yaml_returns_none():
    zip_bytes = _make_zip({"readme.txt": b"nothing here"})
    assert parse_extension_zip(zip_bytes, ext_display_name="Meraki") is None
