"""Smoke and end-to-end sanity tests.

The other test modules are focused unit tests. These verify that the package
imports cleanly and that the CLI orchestration wires the pieces together
correctly — credentials -> auth -> client -> extension resolution -> payload
build -> create — with all external I/O mocked.
"""
from __future__ import annotations

import sys
from unittest import mock

import pytest

import dynatrace_extension_alert_config as pkg
from dynatrace_extension_alert_config import auth, cli
from dynatrace_extension_alert_config.models import ExtensionInfo, FeatureSet, Metric

# ── Smoke: the package and its modules import and wire up ────────────────────

def test_package_has_version():
    assert isinstance(pkg.__version__, str) and pkg.__version__


def test_all_modules_import():
    # Importing the CLI pulls in every sibling module; a syntax/wiring error
    # anywhere would fail here.
    import importlib

    for name in [
        "anomaly", "auth", "client", "config",
        "extension_yaml", "extensions", "interactive", "models", "recommendations",
    ]:
        importlib.import_module(f"dynatrace_extension_alert_config.{name}")


def test_console_entry_point_is_callable():
    assert callable(cli.main)


def test_arg_parser_requires_name(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["dynatrace-extension-alert-config"])
    with pytest.raises(SystemExit):
        cli._parse_args()


def test_arg_parser_parses_flags(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "Meraki", "--env-id", "abc12345",
        "--query-offset", "5", "--dry-run",
    ])
    args = cli._parse_args()
    assert args.name == "Meraki"
    assert args.env_id == "abc12345"
    assert args.query_offset == 5
    assert args.dry_run is True


# ── End-to-end orchestration (all I/O mocked) ────────────────────────────────

class _FakeClient:
    """Stand-in for DynatraceClient that records created/deleted objects."""
    def __init__(self, *_, existing=None, **__):
        self.created: list[dict] = []
        self.deleted: list[str] = []
        # existing: list of {"objectId":..., "value": {...}}
        self.existing = existing or []

    def get_schema(self, schema_id):
        return {"schemaId": schema_id}

    def create_settings_object(self, payload):
        self.created.append(payload)
        return "vu9-OBJECT-ID"

    def list_settings_objects(self, schema_id):
        return self.existing

    def delete_settings_object(self, object_id):
        self.deleted.append(object_id)


@pytest.fixture
def sample_extension():
    return ExtensionInfo(
        name="Meraki Extension",
        version="2.3.1",
        feature_sets=[
            FeatureSet("device-cpu", [
                Metric(key="meraki.device.cpu_usage", name="CPU Usage",
                       feature_set="device-cpu", dimensions=["device.name"], unit="Percent"),
            ]),
        ],
    )


def _patch_common(monkeypatch, fake_client, sample_extension):
    creds = {
        "clientId": "dt0s02.X", "clientSecret": "s",
        "resource": "urn:dtaccount:abc", "environmentUrl": "https://abc.live.dynatrace.com",
    }
    monkeypatch.setattr(cli, "get_or_prompt_credentials", lambda **_: creds)
    monkeypatch.setattr(auth, "get_token_with_fallback", lambda *a, **k: ("tok", True, "scopes"))
    monkeypatch.setattr(auth, "get_bearer_token", lambda *a, **k: "tok")
    monkeypatch.setattr(cli, "DynatraceClient", lambda **_: fake_client)
    monkeypatch.setattr(cli, "resolve_extension", lambda name, client: sample_extension)


def test_end_to_end_yes_creates_davis_detector(monkeypatch, sample_extension):
    fake = _FakeClient()
    _patch_common(monkeypatch, fake, sample_extension)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "Meraki Extension", "--env-id", "abc12345", "--yes",
    ])

    cli.main()

    assert len(fake.created) == 1
    payload = fake.created[0]
    assert payload["schemaId"] == "builtin:davis.anomaly-detectors"
    assert payload["value"]["title"] == "Meraki Extension - CPU Usage"
    # --yes uses Auto-Adaptive / Above with no split dimensions
    assert payload["value"]["analyzer"]["name"].endswith("AutoAdaptiveAnomalyDetectionAnalyzer")


def test_dry_run_creates_nothing(monkeypatch, sample_extension):
    fake = _FakeClient()
    _patch_common(monkeypatch, fake, sample_extension)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "Meraki Extension", "--env-id", "abc12345", "--yes", "--dry-run",
    ])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert fake.created == []  # dry-run must not POST


def test_dump_schema_exits_without_resolving(monkeypatch, sample_extension):
    fake = _FakeClient()
    _patch_common(monkeypatch, fake, sample_extension)
    # If resolve_extension were called, this would blow up — assert it isn't.
    monkeypatch.setattr(cli, "resolve_extension",
                        mock.Mock(side_effect=AssertionError("should not resolve")))
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "x", "--env-id", "abc12345", "--dump-schema",
    ])

    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert fake.created == []


def test_idempotency_skips_existing(monkeypatch, sample_extension):
    # Pre-seed the env with the exact detector --yes would create, so the
    # second run must skip it (no duplicate POST).
    from dynatrace_extension_alert_config.anomaly import build_payload
    from dynatrace_extension_alert_config.interactive import run_auto_flow

    choice = run_auto_flow(sample_extension)[0]
    existing_value = build_payload(choice, "Meraki Extension", query_offset=1)["value"]

    fake = _FakeClient(existing=[{"objectId": "obj-1", "value": existing_value}])
    _patch_common(monkeypatch, fake, sample_extension)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "Meraki Extension", "--env-id", "abc12345", "--yes",
    ])

    cli.main()
    assert fake.created == []  # identical config already exists -> skipped


def test_undo_deletes_tool_created(monkeypatch, sample_extension):
    tool = "dynatrace-extension-alert-config"
    existing = [
        {"objectId": "obj-keep", "value": {"title": "Other Ext - X", "source": tool}},
        {"objectId": "obj-del", "value": {"title": "Meraki Extension - CPU Usage", "source": tool}},
        {"objectId": "obj-foreign", "value": {"title": "Meraki Extension - CPU Usage", "source": "someone-else"}},
    ]
    fake = _FakeClient(existing=existing)
    _patch_common(monkeypatch, fake, sample_extension)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--name", "Meraki Extension", "--env-id", "abc12345", "--undo", "--yes",
    ])

    # --undo returns (no SystemExit) after deleting
    cli.main()
    # Only the tool-created object whose title matches the extension prefix
    assert fake.deleted == ["obj-del"]
