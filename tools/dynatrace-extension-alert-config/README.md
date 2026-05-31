# dynatrace-extension-alert-config

> Bulk-create **Davis Anomaly Detection** configurations for every metric shipped by a Dynatrace extension — interactively, from your terminal.

This CLI reads an extension's metric catalog straight from your Dynatrace environment, lets you choose which metrics to alert on (and how), and creates one **`builtin:davis.anomaly-detectors`** settings object per metric using a DQL `timeseries` query.

---

## Table of contents

1. [Why this tool exists](#1-why-this-tool-exists)
2. [Key concepts (Dynatrace primer)](#2-key-concepts-dynatrace-primer)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [First-run setup & credential storage](#5-first-run-setup--credential-storage)
6. [OAuth scopes — what each one is for](#6-oauth-scopes--what-each-one-is-for)
7. [Command-line usage & flags](#7-command-line-usage--flags)
8. [The interactive flow, step by step](#8-the-interactive-flow-step-by-step)
9. [What gets created — anatomy of a detector](#9-what-gets-created--anatomy-of-a-detector)
10. [Detection models explained](#10-detection-models-explained)
11. [Thresholds & sample windows — what is set and why](#11-thresholds--sample-windows--what-is-set-and-why)
12. [What is set automatically vs. what you must set yourself](#12-what-is-set-automatically-vs-what-you-must-set-yourself)
13. [How an extension is resolved](#13-how-an-extension-is-resolved)
14. [Verifying the result](#14-verifying-the-result)
15. [Troubleshooting](#15-troubleshooting)
16. [Limitations](#16-limitations)

See also: [**Configuration Reference**](docs/CONFIGURATION-REFERENCE.md) — an exhaustive, field-by-field breakdown of the generated payload.

---

## 1. Why this tool exists

A Dynatrace **Extension 2.0** can publish dozens — sometimes hundreds — of metrics, organized into **feature sets** (for example `device-cpu`, `device-memory`, `device-uplink`). Out of the box, ingesting those metrics gives you *data*, but **not alerting**. Davis only raises problems on a metric once you create an **anomaly detector** for it.

Doing that by hand in the UI is slow and error-prone:

- You must locate each metric key (often namespaced, e.g. `com.dynatrace.extension.network_device.cpu_usage`).
- For each one you re-enter the same DQL query shape, sample windows, alert direction, and event template.
- Extensions with many feature sets multiply the effort, and it has to be repeated whenever you onboard the extension into a new environment.

This tool removes that toil. It:

1. **Discovers** the extension's complete metric catalog (and each metric's dimensions and feature set) directly from the deployed extension.
2. Lets you **select** which metrics to monitor and pick a detection model per metric.
3. **Generates and submits** a correct `builtin:davis.anomaly-detectors` object for each, with a consistent naming and event-template convention.

The result is repeatable, reviewable (use `--dry-run`), and fast.

---

## 2. Key concepts (Dynatrace primer)

If you're new to the moving parts, here's the vocabulary this tool touches:

| Concept | What it means here |
|---|---|
| **Davis Anomaly Detection (app)** | The modern, DQL-based anomaly detection in Dynatrace SaaS. Detectors are stored as Settings 2.0 objects under the schema `builtin:davis.anomaly-detectors`. **This is *not* the older "Metric events" (`builtin:anomaly-detection.metric-events`).** |
| **Analyzer** | The detection model behind a detector. Three exist: `StaticThreshold`, `AutoAdaptiveBaseline`, `SeasonalBaseline`. |
| **DQL `timeseries` query** | The detector evaluates a Grail DQL query, not a metric selector. The query produces a 1-minute-interval series plus a `scalar` measure (`value.A`) that the analyzer scores. |
| **Feature set** | A grouping of metrics defined in the extension. Used here only to organize the selection list; it does not affect the detector. |
| **Dimension** | A metric's split key (e.g. `device.name`, `interface`). Splitting `by:{…}` creates one detector evaluation per dimension value, so a single config covers every device/interface. |
| **Event template** | The content of the problem Davis raises (event name, description). Supports placeholders like `{dims:…}`, `{alert_condition}`, `{threshold}`. |
| **Settings 2.0 objects API** | `POST /api/v2/settings/objects` — how the detector is created. Returns a per-object result array. |
| **OAuth client (client-credentials)** | The SaaS authentication used here, exchanged at `sso.dynatrace.com` for a short-lived bearer token. |

---

## 3. Prerequisites

Before you run the tool, make sure all of the following are true:

- **A Dynatrace SaaS environment.** Davis Anomaly Detection (the DQL app) is **not available on Dynatrace Managed**, so this tool is SaaS-only.
- **The Davis Anomaly Detection app is available** in your environment (the `builtin:davis.anomaly-detectors` schema must exist — the tool checks this on startup).
- **The extension is installed/active** in that environment. The tool reads the metric catalog from the deployed extension package, so it must be present.
- **An OAuth client** (Account Management → Identity & access management → OAuth clients) with:
  - your **Client ID** and **Client Secret**,
  - your **account URN** (`urn:dtaccount:<uuid>`) used as the `resource`,
  - the five **scopes** listed in [section 6](#6-oauth-scopes--what-each-one-is-for).
- **Your environment URL / ID**, e.g. `https://abc12345.live.dynatrace.com` (or just `abc12345`).
- **Python 3.10+**.

---

## 4. Installation

```bash
pip install -e tools/dynatrace-extension-alert-config/
```

This exposes the `dynatrace-extension-alert-config` console command. Dependencies: `requests`, `questionary`, `rich`, `pyyaml`.

---

## 5. First-run setup & credential storage

On the **first run** (or any run with `--reconfigure`) the tool prompts for four values and stores them locally:

```
Client ID:        dt0s02.XXXXXXXXXX
Client Secret:    ••••••••••••••••••   (input hidden)
Resource:         urn:dtaccount:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Environment URL:  https://<env-id>.live.dynatrace.com
```

| Prompt | What it is | Where to find it |
|---|---|---|
| **Client ID** | OAuth client identifier | Account Management → Identity & access management → OAuth clients |
| **Client Secret** | OAuth client secret | shown once when the client is created |
| **Resource** | Your **account URN**, scopes the token to your account | Account Management → Account info (`urn:dtaccount:<uuid>`) |
| **Environment URL** | Base URL of the target environment | your tenant URL (`https://<env-id>.live.dynatrace.com`) |

### Storage location & security

Credentials are written to:

```
~/.dynatrace/extensions/OAuth.json     (file mode 0600, directories 0700)
```

```json
{
  "clientId": "dt0s02.XXXXXXXXXX",
  "clientSecret": "...",
  "resource": "urn:dtaccount:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environmentUrl": "https://<env-id>.live.dynatrace.com"
}
```

- The file is created **owner-read/write only** (`0600`).
- The folder layout (`~/.dynatrace/<tool>/…`) is per-tool by design, so other Dynatrace tools can store their own credentials alongside without collision.
- **Bearer tokens are never written to disk.** They are fetched fresh from `sso.dynatrace.com` each run, cached in memory, valid ~5 minutes, and transparently re-issued if they expire mid-session.

---

## 6. OAuth scopes — what each one is for

Assign **all five** to your OAuth client. If even one requested scope is missing/invalid, Dynatrace SSO rejects the **entire** token request with `HTTP 400`.

| Scope | Why it's needed |
|---|---|
| `settings:schemas:read` | Read the `builtin:davis.anomaly-detectors` schema (also used as the startup connectivity check). |
| `settings:objects:read` | Read existing settings objects. |
| `settings:objects:write` | **Create** the anomaly detectors. |
| `environment-api:extensions:read` | List installed extensions and **download the extension package** (`extension.yaml`) to read the metric catalog. *(This is the classic Environment API scope — **not** the platform `extensions:definitions:read`.)* |
| `storage:metrics:read` | The detector evaluates a **DQL `timeseries`** query over Grail metrics; creating it requires metric read access. |

**Graceful degradation:** if the full set is rejected, the tool retries with only the three `settings:*` scopes so detector creation can still proceed — but extension discovery via the environment API will then fail (and it warns you). Override the requested set with `--scopes "…"`.

---

## 7. Command-line usage & flags

```bash
# Interactive (default)
dynatrace-extension-alert-config --name "Meraki Extension" --env-id abc12345

# The name is forgiving — casing and a trailing "extension" word are ignored
dynatrace-extension-alert-config --name meraki --env-id abc12345

# Preview the exact JSON without creating anything
dynatrace-extension-alert-config --name meraki --env-id abc12345 --dry-run

# Non-interactive: Auto-Adaptive / Above for every metric, no splits
dynatrace-extension-alert-config --name meraki --env-id abc12345 --yes

# Print the live schema (ground truth for the payload shape) and exit
dynatrace-extension-alert-config --name meraki --env-id abc12345 --dump-schema
```

| Flag | Default | Effect |
|---|---|---|
| `--name` | *(required)* | Extension name as shown on the Hub. Fuzzy-matched; casing and a trailing "extension" word are ignored. |
| `--env-id` | stored value | Environment ID (e.g. `abc12345`) → builds `https://<env-id>.live.dynatrace.com` and overrides the stored `environmentUrl` for this run only. |
| `--query-offset` | `1` | Detector query offset in minutes (1-60). See [section 11](#11-thresholds--sample-windows--what-is-set-and-why). |
| `--scopes` | the five above | Override the OAuth scopes requested. Only add scopes your client actually has. |
| `--reconfigure` | off | Re-enter and re-save the OAuth credentials. |
| `--dry-run` | off | Print the JSON payloads (annotated with would-CREATE / would-SKIP); make **no** API calls. |
| `--yes` | off | Non-interactive: create an **Auto-Adaptive Baseline / Above** detector for **every** metric, with **no** split dimensions. Also skips the `--undo` confirmation. |
| `--undo` | off | **Delete** the detectors this tool created for `--name`. Confirms first unless `--yes`. |
| `--dump-schema` | off | Print the live `builtin:davis.anomaly-detectors` schema JSON and exit. |

### Safe to run twice (idempotency)

Re-running the tool will **not** create duplicate detectors. Before creating, it reads the existing `builtin:davis.anomaly-detectors` objects and classifies each metric:

- **identical** — a detector with the same title *and* the same model / threshold / query already exists → **skipped**.
- **differs** — a detector with the same name exists but with different settings (e.g. you changed the threshold) → **skipped and flagged**, so you're never surprised by a silent duplicate. To replace it, `--undo` then re-run.
- **new** — created.

A summary line reports `created / already existed / differ / failed`.

### Undoing

```bash
# Remove everything this tool created for an extension (asks for confirmation first)
dynatrace-extension-alert-config --name "Meraki Extension" --env-id abc12345 --undo

# Skip the confirmation
dynatrace-extension-alert-config --name "Meraki Extension" --env-id abc12345 --undo --yes
```

Undo only ever touches objects **this tool created** (matched by the `source: dynatrace-extension-alert-config` tag) **and** whose name starts with `<Extension> - `, so it never deletes detectors you built by hand or for other extensions.

---

## 8. The interactive flow, step by step

1. **Authenticate** — exchange your OAuth client for a bearer token at `sso.dynatrace.com`.
2. **Connectivity check** — read the `builtin:davis.anomaly-detectors` schema to confirm access and that the app is present.
3. **Resolve the extension** — fuzzy-match `--name`, download the extension package, and parse `extension.yaml` into feature sets → metrics → dimensions.
4. **Summary table** — every metric is listed with its feature set, key, display name, and dimensions.
5. **Metric selection** — a checkbox list (grouped by feature set). Space toggles, Enter confirms.
6. **Per-metric configuration**, for each selected metric:
   - **Detection model** — Auto-Adaptive Baseline / Seasonal Baseline / Static Threshold.
   - **Alert direction** — Above / Below.
   - **Threshold value** *(static only)* — numeric. If the metric's unit is recognizable (e.g. a percentage), a **recommended default is pre-filled** — press Enter to accept or type your own. See [Unit-based threshold recommendations](#unit-based-threshold-recommendations).
   - **Split dimension(s)** — a checkbox of that metric's dimensions (or skip for no split).
7. **Create** — one `POST /api/v2/settings/objects` per metric. A results table shows Created (with Object ID) or Failed (with the full validation error printed below the table).

---

## 9. What gets created — anatomy of a detector

Each selected metric becomes **one** `builtin:davis.anomaly-detectors` settings object:

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "environment",
  "value": {
    "enabled": true,
    "title": "Meraki Extension - Meraki Appliance CPU Usage",
    "description": "Auto-created for Meraki Extension metric meraki.device.cpu_usage",
    "source": "dynatrace-extension-alert-config",
    "analyzer": {
      "name": "dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer",
      "input": [
        {"key": "query", "value": "timeseries { avg(meraki.device.cpu_usage), value.A = avg(meraki.device.cpu_usage, scalar: true) }, by: { device.name }, interval: 1m"},
        {"key": "alertCondition", "value": "ABOVE"},
        {"key": "alertOnMissingData", "value": "false"},
        {"key": "violatingSamples", "value": "3"},
        {"key": "slidingWindow", "value": "5"},
        {"key": "dealertingSamples", "value": "5"},
        {"key": "threshold", "value": "80"}
      ]
    },
    "executionSettings": {"queryOffset": 1},
    "eventTemplate": {
      "properties": [
        {"key": "event.name", "value": "Meraki Extension - Meraki Appliance CPU Usage on {dims:device.name} is {alert_condition} the threshold of {threshold}"},
        {"key": "event.description", "value": "The metric meraki.device.cpu_usage is {alert_condition} the threshold of {threshold}."}
      ]
    }
  }
}
```

**Naming conventions:**

- **Configuration name** (`value.title`) = `<Extension> - <Metric display name>`
- **Event name** (`event.name`) = `<Extension> - <Metric display name> on {dims:<dim>} is {alert_condition} the threshold of {threshold}` — the ` on …` clause is dropped when you split by nothing.

**The DQL query:**

```
timeseries { avg(<metricKey>), value.A = avg(<metricKey>, scalar: true) }, by: { <dims> }, interval: 1m
```

- `avg(<metricKey>)` — the charted series shown on the event.
- `value.A = avg(<metricKey>, scalar: true)` — the **scalar** measure the analyzer actually scores.
- `by: { … }` — present only when you chose split dimensions; each value becomes an independently-evaluated series.
- `interval: 1m` — **mandatory** for Davis anomaly detectors.

> Aggregation is always `avg`. To use `sum`/`min`/`max`/etc., edit the detector after creation (see [section 12](#12-what-is-set-automatically-vs-what-you-must-set-yourself)).

**Placeholders** (`{alert_condition}`, `{threshold}`, `{dims:<dim>}`) are resolved by Dynatrace at event-fire time.

---

## 10. Detection models explained

You pick one model per metric. In `builtin:davis.anomaly-detectors` each maps to a named analyzer:

| Model (CLI) | Analyzer | When to use it | Needs a threshold? |
|---|---|---|---|
| **Static Threshold** | `StaticThresholdAnomalyDetectionAnalyzer` | You know the exact value that means trouble (e.g. CPU > 80%, loss > 0). Deterministic and simple. | **Yes** — you enter it. |
| **Auto-Adaptive Baseline** | `AutoAdaptiveAnomalyDetectionAnalyzer` | The "normal" value drifts over time and you want Davis to learn it automatically. Good default for most metrics. | No |
| **Seasonal Baseline** | `SeasonalBaselineAnomalyDetectionAnalyzer` | The metric has time-of-day / day-of-week patterns (business traffic, batch cycles) that a flat baseline would mis-flag. | No |

For all three you also choose the **alert direction** — `ABOVE` or `BELOW` the threshold/baseline.

---

## 11. Thresholds & sample windows — what is set and why

Every detector carries a set of **sample-window** parameters that govern *how persistently* a metric must misbehave before Davis opens (or closes) a problem. The tool sets these defaults:

| Parameter | Default | Dynatrace meaning | Why this default |
|---|---|---|---|
| `slidingWindow` | **5** | The size of the evaluation window, in 1-minute samples. Davis looks at the last *5* minutes at any moment. | Five minutes smooths out single-sample spikes while staying responsive. |
| `violatingSamples` | **3** | How many of those samples (within the window) must breach the threshold/baseline to **open** a problem. | 3-of-5 means a clear majority — enough to filter transient blips, not so many that real issues are missed. Must be <= `slidingWindow`. |
| `dealertingSamples` | **5** | How many consecutive samples must return to normal to **close** the problem. | Requiring a full clean window prevents a problem from flapping open/closed on noisy data. |
| `alertOnMissingData` | **false** | Whether a gap in data is treated as a violation. | Off by default so that a metric simply not reporting (e.g. a powered-off device) doesn't generate alert noise. Turn it on in the app if "no data" is itself a problem. |
| `queryOffset` (`executionSettings`) | **1** (override with `--query-offset`) | Minutes to shift the evaluation window into the past. The schema **requires** 1-60. | Metrics arrive with some ingest latency; evaluating a slightly-delayed window means Davis scores **complete** data rather than a minute that's still filling. `1` is the minimum the schema allows — there is no "zero offset". |
| `threshold` *(static only)* | *(you provide it)* | The fixed value compared against each sample, in the metric's own unit. | Domain-specific — only you know what value is "bad". |

> **These are sensible starting points, not gospel.** `slidingWindow`, `violatingSamples`, `dealertingSamples`, and `alertOnMissingData` are currently **hardcoded defaults** in the tool. To change them, either edit the detector in the Davis Anomaly Detection app after creation, or adjust the constants in `anomaly.py`. Only `queryOffset` is exposed as a flag (`--query-offset`).

### Unit-based threshold recommendations

For a **Static Threshold** detector you still have to pick the threshold value — but the tool can pre-fill a sensible starting point **without any AI**, purely from the metric's declared `unit`.

Extension metrics carry a `unit` in their `extension.yaml` metadata (for example `Percent`, `Ratio`, `MilliSecond`, `Byte`). When the unit has an unambiguous, bounded range, the tool suggests a default based on the alert direction you chose:

| Metric unit | Range | Recommended for **Above** | Recommended for **Below** |
|---|---|---|---|
| `Percent` (e.g. `%`) | 0-100 | **80** | **20** |
| `Ratio` | 0-1 | **0.8** | **0.2** |
| anything else | unknown | *(no pre-fill — you type the value)* | *(no pre-fill)* |

So for a metric like `device.cpu_usage` reported in `Percent`, choosing **Above** pre-fills `80`; press Enter to accept or type your own. The recommendation is only a **default** — it never overrides what you type, and unknown units simply leave the field blank. The metric's unit is also shown in the selection summary table and in the threshold prompt so you always have the context.

> Why only these units? A percentage or ratio has a fixed, well-understood range, so "alert above 80%" is defensible for any percentage metric. Units like milliseconds or bytes have no universal "bad" value, so the tool deliberately makes no guess. To adjust the recommended values or add more units, edit `recommendations.py`.

---

## 12. What is set automatically vs. what you must set yourself

### Chosen interactively (per metric), every run
- **Which metrics** get a detector (checkbox).
- **Detection model** (static / auto-adaptive / seasonal).
- **Alert direction** (above / below).
- **Threshold value** (static model only) — pre-filled with a unit-based recommendation you can accept or override.
- **Split dimension(s)**.

### Set automatically by the tool (fixed conventions)
- Schema `builtin:davis.anomaly-detectors`, scope `environment`, `enabled: true`.
- **Config name** and **event name/description** (the naming convention in [section 9](#9-what-gets-created--anatomy-of-a-detector)).
- DQL query shape with `avg()` aggregation and `interval: 1m`.
- `source: dynatrace-extension-alert-config` (so you can filter all tool-created detectors in the app).
- Sample-window defaults from [section 11](#11-thresholds--sample-windows--what-is-set-and-why).
- `queryOffset` (defaults to 1, or `--query-offset`).

### Must be set/changed by you (not auto-detected — edit after creation)
- **A non-`avg` aggregation** (sum/min/max/count/percentile).
- **Different sample windows** (`slidingWindow`, `violatingSamples`, `dealertingSamples`) or **alert-on-missing-data**.
- **Custom entity filters / additional DQL** beyond a straight metric split.
- **Per-detector event metadata** beyond name + description.
- **Disabling or tuning** individual detectors over time.

All of the above are editable in **Davis Anomaly Detection → (the config)** after creation, or via the Settings API.

---

## 13. How an extension is resolved

The metric catalog is read **only** from the connected environment via the Extensions 2.0 API (authoritative). The extension must be installed/active in that environment.

1. List installed extensions (`GET /api/v2/extensions`) and **fuzzy-match** your `--name` to a fully-qualified id (e.g. `com.dynatrace.extension.meraki`).
2. Resolve its active version, then **download the extension package** and read `extension.yaml`.
3. Parse the metric catalog:
   - **Metric keys** come **only** from the top-level `metrics:` block and from `metrics:` lists inside feature-set / group / subgroup definitions — never from arbitrary `key:` fields (so dimensions, topology, charts, and template vars are correctly excluded).
   - **Feature set** per metric, applying inheritance: *metric > subgroup > group > `default`*.
   - **Dimensions** per metric: from the metric's `metadata.dimensions` **plus** inherited group/subgroup `dimensions`.

If the extension can't be resolved (not installed, name mismatch, or the token lacks `environment-api:extensions:read`), the run stops with an actionable error.

---

## 14. Verifying the result

After a successful run, confirm in the UI:

> **Davis Anomaly Detection** app → your new configs (filter by source `dynatrace-extension-alert-config`).

Or via API:

```bash
GET /api/v2/settings/objects?schemaIds=builtin:davis.anomaly-detectors&scopes=environment
```

Trigger or wait for a test event and confirm the **event name** renders the placeholders (`{dims:…}`, `{alert_condition}`, `{threshold}`) rather than showing them literally.

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `OAuth 400 Bad Request` at startup | A requested scope is invalid or not granted; SSO rejects the whole request. | Grant all five scopes ([section 6](#6-oauth-scopes--what-each-one-is-for)); confirm `resource` is your account URN. |
| `403 Forbidden` on `/api/v2/extensions` | Token lacks `environment-api:extensions:read`. | Add that scope. The error now prints the exact required scope. |
| `Could not resolve extension …` | Extension not installed, name mismatch, or the token lacks `environment-api:extensions:read`. | Confirm the extension is installed, check the name, and grant the extensions read scope. |
| Create fails with `Validation failed for N Validators` | A payload field doesn't match the live schema. | The full message is printed under **Errors**. Run `--dump-schema` to compare against your tenant's schema. |
| `queryOffset: Value must be between 1 and 60` | Offset out of range. | Use `--query-offset` with 1-60. |
| `Access Token is invalid` on create | Token expired during a long interactive session. | Already handled — the client refreshes the token per request. If you still see it, re-run. |

---

## 16. Limitations

- **SaaS only** — relies on the `sso.dynatrace.com` OAuth flow and the DQL Davis Anomaly Detection app, neither of which exists on Dynatrace Managed.
- **`avg` aggregation only** at creation time (editable afterward).
- **Uniform sample-window defaults** across all created detectors (editable afterward).
- The extension must be **installed** in the target environment for metric discovery.
- One detector is created **per metric** (split dimensions are handled inside a single detector via `by:{…}`).
