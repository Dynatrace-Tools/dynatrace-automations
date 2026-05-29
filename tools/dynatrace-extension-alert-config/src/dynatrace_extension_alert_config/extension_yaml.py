"""Parse an Extensions 2.0 ``extension.yaml`` into feature sets and metrics.

The classic ``/api/v2/extensions/{name}/{version}`` JSON only returns feature-set
*names*, not the metric keys. The authoritative source for the metric-key ->
feature-set mapping is the extension's ``extension.yaml``, which we obtain by
downloading the extension package (a zip) and reading that file.

extension.yaml shape (datasource-dependent), simplified::

    metrics:                       # top-level: metric metadata
      - key: meraki.device.cpu_usage
        metadata:
          displayName: Meraki Appliance CPU Usage
          description: CPU Usage ...

    <datasource>:                  # e.g. python, snmp, sql, prometheus, wmi
      ...
        - featureSet: device-cpu   # feature set assigned to a group/subgroup
          ...
          metrics:
            - key: meraki.device.cpu_usage

Feature sets are inherited: a metric inherits the subgroup's feature set, which
inherits the group's. A more specific ``featureSet`` overrides a less specific
one. Metrics with no feature set anywhere are reported as ``default``.
"""
from __future__ import annotations
import io
import zipfile
from typing import Optional

import yaml

from .models import ExtensionInfo, FeatureSet, Metric

DEFAULT_FEATURE_SET = "default"


def _find_extension_yaml(zip_bytes: bytes) -> Optional[str]:
    """Return the extension.yaml text from an extension zip.

    The Dynatrace extension package nests the actual extension content in an
    inner ``extension.zip`` (signed bundle). Handle both flat and nested cases.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()

        # Direct extension.yaml
        for n in names:
            if n.endswith("extension.yaml") or n.endswith("extension.yml"):
                return zf.read(n).decode("utf-8", errors="replace")

        # Nested extension.zip -> recurse
        for n in names:
            if n.endswith("extension.zip"):
                inner = _find_extension_yaml(zf.read(n))
                if inner:
                    return inner
    return None


def _collect_metric_metadata(doc: dict) -> dict[str, Metric]:
    """Read the top-level ``metrics:`` list for display name + description."""
    out: dict[str, Metric] = {}
    for m in doc.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        key = m.get("key")
        if not key:
            continue
        meta = m.get("metadata", {}) or {}
        out[key] = Metric(
            key=key,
            name=meta.get("displayName", "") or key,
            description=meta.get("description", "") or "",
        )
    return out


def _walk_feature_sets(node, inherited_fs: str, mapping: dict[str, str]) -> None:
    """Recursively assign feature sets to metric keys, honoring inheritance.

    Carries the nearest ``featureSet`` down the tree. A metric node (a dict
    with a string ``key``) is assigned the most specific feature set in scope.
    A non-default assignment never gets overwritten by a default one.
    """
    if isinstance(node, dict):
        current_fs = node.get("featureSet", inherited_fs)
        if isinstance(current_fs, str) and current_fs:
            pass
        else:
            current_fs = inherited_fs

        key = node.get("key")
        if isinstance(key, str) and key:
            assigned = node.get("featureSet", current_fs)
            if not isinstance(assigned, str) or not assigned:
                assigned = current_fs
            existing = mapping.get(key)
            if existing is None or (existing == DEFAULT_FEATURE_SET and assigned != DEFAULT_FEATURE_SET):
                mapping[key] = assigned

        for k, v in node.items():
            if k in ("metadata",):  # metadata never carries metric structure
                continue
            _walk_feature_sets(v, current_fs, mapping)
    elif isinstance(node, list):
        for item in node:
            _walk_feature_sets(item, inherited_fs, mapping)


def parse_extension_yaml(text: str, ext_display_name: str) -> ExtensionInfo:
    doc = yaml.safe_load(text) or {}

    metadata = _collect_metric_metadata(doc)

    # Build metric -> feature set across the whole document (datasource sections).
    fs_mapping: dict[str, str] = {}
    _walk_feature_sets(doc, DEFAULT_FEATURE_SET, fs_mapping)

    # Union of all known metric keys: those with metadata and those discovered
    # in datasource definitions.
    all_keys = set(metadata) | set(fs_mapping)

    by_fs: dict[str, list[Metric]] = {}
    for key in sorted(all_keys):
        metric = metadata.get(key) or Metric(key=key, name=key, description="")
        fs_name = fs_mapping.get(key, DEFAULT_FEATURE_SET)
        metric.feature_set = fs_name
        by_fs.setdefault(fs_name, []).append(metric)

    feature_sets = [FeatureSet(name=name, metrics=ms) for name, ms in sorted(by_fs.items())]
    version = str(doc.get("version", "") or "")
    return ExtensionInfo(name=ext_display_name, version=version, feature_sets=feature_sets)


def parse_extension_zip(zip_bytes: bytes, ext_display_name: str) -> Optional[ExtensionInfo]:
    text = _find_extension_yaml(zip_bytes)
    if not text:
        return None
    info = parse_extension_yaml(text, ext_display_name)
    return info if info.feature_sets else None
