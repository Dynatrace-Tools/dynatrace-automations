"""Parse an Extensions 2.0 ``extension.yaml`` into feature sets and metrics.

The classic ``/api/v2/extensions/{name}/{version}`` JSON only returns feature-set
*names*, not the metric keys. The authoritative source for the metric-key ->
feature-set mapping is the extension's ``extension.yaml``, which we obtain by
downloading the extension package (a zip) and reading that file.

Per the Dynatrace docs, **metric keys appear only in two places**:

1. The top-level ``metrics:`` block — the canonical list of metric keys, each
   with ``metadata`` (displayName, description, unit)::

       metrics:
         - key: meraki.device.cpu_usage
           metadata:
             displayName: Meraki Appliance CPU Usage
             description: CPU Usage ...

2. Inside ``metrics:`` lists within feature-set / group / subgroup definitions,
   which is what assigns a metric to a feature set. Two layouts exist:

   - Python extensions: a top-level ``featureSets:`` list::

         featureSets:
           - featureSet: device-cpu
             metrics:
               - key: meraki.device.cpu_usage

   - SNMP / SQL / Prometheus / WMI: ``featureSet`` on a group/subgroup,
     inherited by the nested ``metrics:`` list::

         snmp:
           - featureSet: device-cpu
             subgroups:
               - metrics:
                   - key: meraki.device.cpu_usage

Crucially, every OTHER ``key`` in the file — dimensions, topology attributes,
entity/chart/DQL definitions — is **not** a metric and must be ignored. We
therefore only ever read keys from the top-level ``metrics:`` block and from
``metrics:`` lists, never from arbitrary ``key`` fields.

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


def _dimension_keys(container: dict) -> list[str]:
    """Extract dimension keys from a ``dimensions:`` list on a dict."""
    keys: list[str] = []
    for d in container.get("dimensions", []) or []:
        if isinstance(d, dict):
            k = d.get("key")
            if isinstance(k, str) and k:
                keys.append(k)
        elif isinstance(d, str):
            keys.append(d)
    return keys


def _collect_metric_metadata(doc: dict) -> dict[str, Metric]:
    """Read the top-level ``metrics:`` list for the canonical metric keys, their
    display name + description, and any dimensions declared in metadata."""
    out: dict[str, Metric] = {}
    for m in doc.get("metrics", []) or []:
        if not isinstance(m, dict):
            continue
        key = m.get("key")
        if not isinstance(key, str) or not key:
            continue
        meta = m.get("metadata", {}) or {}
        out[key] = Metric(
            key=key,
            name=meta.get("displayName", "") or key,
            description=meta.get("description", "") or "",
            dimensions=_dimension_keys(meta),
        )
    return out


def _assign(mapping: dict[str, str], key: str, feature_set: str) -> None:
    """Record a metric's feature set, preferring a specific one over default."""
    existing = mapping.get(key)
    if existing is None or (existing == DEFAULT_FEATURE_SET and feature_set != DEFAULT_FEATURE_SET):
        mapping[key] = feature_set


def _walk_feature_sets(
    node,
    inherited_fs: str,
    inherited_dims: tuple[str, ...],
    mapping: dict[str, str],
    dim_mapping: dict[str, list[str]],
) -> None:
    """Walk the document, assigning feature sets and split dimensions to metrics.

    Keys are read ONLY from ``metrics:`` lists, never from arbitrary ``key``
    fields, so dimensions/topology/chart keys are never mistaken for metrics.
    The nearest ``featureSet`` in scope is inherited (an entry's own overrides);
    ``dimensions:`` declared on enclosing group/subgroup dicts accumulate and are
    inherited by the metrics they contain.
    """
    if isinstance(node, dict):
        fs = node.get("featureSet")
        current_fs = fs if isinstance(fs, str) and fs else inherited_fs

        current_dims = inherited_dims
        for d in _dimension_keys(node):
            if d not in current_dims:
                current_dims = current_dims + (d,)

        for k, v in node.items():
            if k == "metrics" and isinstance(v, list):
                for item in v:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("key")
                    if not isinstance(key, str) or not key:
                        continue
                    item_fs = item.get("featureSet")
                    assigned = item_fs if isinstance(item_fs, str) and item_fs else current_fs
                    _assign(mapping, key, assigned)
                    # Inherited dims plus any declared on the metric entry itself.
                    metric_dims = list(current_dims)
                    for d in _dimension_keys(item):
                        if d not in metric_dims:
                            metric_dims.append(d)
                    existing = dim_mapping.setdefault(key, [])
                    for d in metric_dims:
                        if d not in existing:
                            existing.append(d)
            elif k == "dimensions":
                continue  # already folded into current_dims
            else:
                _walk_feature_sets(v, current_fs, current_dims, mapping, dim_mapping)
    elif isinstance(node, list):
        for item in node:
            _walk_feature_sets(item, inherited_fs, inherited_dims, mapping, dim_mapping)


def parse_extension_yaml(text: str, ext_display_name: str) -> ExtensionInfo:
    doc = yaml.safe_load(text) or {}

    metadata = _collect_metric_metadata(doc)

    # metric key -> feature set / dimensions, harvested only from metrics: lists.
    fs_mapping: dict[str, str] = {}
    dim_mapping: dict[str, list[str]] = {}
    _walk_feature_sets(doc, DEFAULT_FEATURE_SET, (), fs_mapping, dim_mapping)

    # Authoritative metric set = top-level metrics block plus any key referenced
    # in a metrics: list. Both sources are real metrics; nothing else qualifies.
    all_keys = set(metadata) | set(fs_mapping)

    by_fs: dict[str, list[Metric]] = {}
    for key in sorted(all_keys):
        metric = metadata.get(key) or Metric(key=key, name=key, description="")
        metric.feature_set = fs_mapping.get(key, DEFAULT_FEATURE_SET)
        # Merge metadata dimensions with those inherited from groups/subgroups.
        merged = list(metric.dimensions)
        for d in dim_mapping.get(key, []):
            if d not in merged:
                merged.append(d)
        metric.dimensions = merged
        by_fs.setdefault(metric.feature_set, []).append(metric)

    feature_sets = [FeatureSet(name=name, metrics=ms) for name, ms in sorted(by_fs.items())]
    version = str(doc.get("version", "") or "")
    return ExtensionInfo(name=ext_display_name, version=version, feature_sets=feature_sets)


def parse_extension_zip(zip_bytes: bytes, ext_display_name: str) -> Optional[ExtensionInfo]:
    text = _find_extension_yaml(zip_bytes)
    if not text:
        return None
    info = parse_extension_yaml(text, ext_display_name)
    return info if info.feature_sets else None

