# Configuration Reference

An exhaustive, field-by-field breakdown of the `builtin:davis.anomaly-detectors` settings object this tool generates. For the narrative overview, see the [README](../README.md).

Every detector is submitted to:

```
POST /api/v2/settings/objects
Authorization: Bearer <oauth-token>
Content-Type: application/json

[ { "schemaId": "...", "scope": "environment", "value": { ... } } ]
```

The response is an **array** (one result per object). On success each item carries `code: 201` and an `objectId`; on failure each item carries `code: 400` and an `error` with `constraintViolations`. The tool inspects the per-item code rather than trusting the HTTP status alone.

---

## Top-level object

| Field | Value set by tool | Editable? | Notes |
|---|---|---|---|
| `schemaId` | `builtin:davis.anomaly-detectors` | No | Fixed — this is the DQL Davis Anomaly Detection schema (not metric-events). |
| `scope` | `environment` | No | Detectors are environment-scoped. |
| `value` | *(object below)* | — | The detector definition. |

---

## `value`

| Field | Value set by tool | Set how | Editable in app? |
|---|---|---|---|
| `enabled` | `true` | fixed | Yes — disable a config without deleting it. |
| `title` | `<Extension> - <Metric display name>` | convention | Yes — this is the **configuration name** in the app. |
| `description` | `Auto-created for <Extension> metric <metricKey>` | convention | Yes |
| `source` | `dynatrace-extension-alert-config` | fixed | Yes — a free-text grouping/filter tag; lets you find all tool-created detectors. |
| `analyzer` | *(object below)* | — | Yes |
| `executionSettings` | `{ "queryOffset": <1-60> }` | flag/default | Yes |
| `eventTemplate` | *(object below)* | — | Yes |

---

## `value.analyzer`

| Field | Value set by tool | Notes |
|---|---|---|
| `name` | one of the three analyzer FQNs below | Chosen by your **detection model** selection. |
| `input` | a **set** (array) of `{ "key", "value" }` pairs | All values are **strings**, even numbers and booleans. See the input table. |

### Analyzer names

| Model (CLI) | `analyzer.name` |
|---|---|
| Static Threshold | `dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer` |
| Auto-Adaptive Baseline | `dt.statistics.ui.anomaly_detection.AutoAdaptiveAnomalyDetectionAnalyzer` |
| Seasonal Baseline | `dt.statistics.ui.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer` |

### `analyzer.input` fields

| `key` | `value` set by tool | Source | Meaning |
|---|---|---|---|
| `query` | the DQL string (below) | generated | The `timeseries` query the analyzer evaluates. |
| `alertCondition` | `ABOVE` / `BELOW` | your choice | Direction that constitutes a violation. |
| `alertOnMissingData` | `"false"` | fixed default | Whether missing samples count as violations. |
| `violatingSamples` | `"3"` | fixed default | Samples in the window that must breach to **open** a problem. |
| `slidingWindow` | `"5"` | fixed default | Evaluation window size, in 1-minute samples. |
| `dealertingSamples` | `"5"` | fixed default | Clean samples required to **close** a problem. |
| `threshold` | the number you entered | static only | The fixed comparison value, in the metric's base unit. Omitted for baseline models. |

### The DQL query

```
timeseries { avg(<metricKey>), value.A = avg(<metricKey>, scalar: true) }, by: { <dim1>, <dim2> }, interval: 1m
```

- `avg(<metricKey>)` — the charted series.
- `value.A = avg(<metricKey>, scalar: true)` — the **scalar** measure the analyzer scores.
- `by: { … }` — only present when split dimensions were chosen.
- `interval: 1m` — mandatory; Davis anomaly detectors require a 1-minute series.
- Aggregation is always `avg` (edit afterward for other aggregations).

---

## `value.executionSettings`

| Field | Value set by tool | Constraints | Meaning |
|---|---|---|---|
| `queryOffset` | `1` (or `--query-offset`) | **integer 1–60** (schema-enforced) | Minutes to shift the evaluation window into the past, so the detector scores fully-ingested data rather than a still-filling current minute. There is no "0" — 1 is the minimum. |

---

## `value.eventTemplate`

The event template is a **set** of `event.*` property pairs (it does **not** use `title`/`description`/`davisMerge`/`eventType` — those belong to the older metric-events schema).

| `properties[].key` | `value` set by tool | Meaning |
|---|---|---|
| `event.name` | `<Extension> - <Metric display name> on {dims:<dim>} is {alert_condition} the threshold of {threshold}` | The problem's title. The ` on {dims:…}` clause is omitted when there are no split dimensions. |
| `event.description` | `The metric <metricKey> is {alert_condition} the threshold of {threshold}.` | The problem's description. |

### Placeholders

Resolved by Dynatrace when an event fires:

| Placeholder | Resolves to |
|---|---|
| `{dims:<dimensionKey>}` | The value of that dimension for the violating series (e.g. the specific device name). |
| `{alert_condition}` | The configured condition (above/below). |
| `{threshold}` | The threshold or computed baseline value at event time. |

> If a placeholder renders **literally** in a fired event, your tenant's schema may use different placeholder names. Run `--dump-schema` and adjust `anomaly.py:build_event_title` / the description accordingly.

---

## Defaults summary — change matrix

| Setting | Default | Change via CLI? | Change in app after creation? | Change in code? |
|---|---|---|---|---|
| Detection model | *(interactive)* | per-metric prompt | yes | — |
| Alert direction | *(interactive)* | per-metric prompt | yes | — |
| Static threshold | *(interactive)* | per-metric prompt | yes | — |
| Split dimensions | *(interactive)* | per-metric prompt | yes | — |
| `queryOffset` | `1` | `--query-offset` | yes | `anomaly.py: DEFAULT_QUERY_OFFSET` |
| `slidingWindow` | `5` | no | yes | `anomaly.py: _analyzer_input` |
| `violatingSamples` | `3` | no | yes | `anomaly.py: _analyzer_input` |
| `dealertingSamples` | `5` | no | yes | `anomaly.py: _analyzer_input` |
| `alertOnMissingData` | `false` | no | yes | `anomaly.py: _analyzer_input` |
| Aggregation | `avg` | no | yes | `anomaly.py: build_dql_query` |
| Config name / event name | convention | no | yes | `anomaly.py: build_event_title` / `_config_title` |
| `source` | `dynatrace-extension-alert-config` | no | yes | `anomaly.py: SOURCE` |
