# dynatrace-extension-alert-config

Create [Davis Anomaly Detection](https://docs.dynatrace.com/docs/discover-dynatrace/platform/davis-ai/anomaly-detection/anomaly-detection-app) configurations for every metric in any Dynatrace extension — interactively, from the CLI.

## What it does

Given an extension name (e.g. `Meraki Extension`), the tool:

1. Looks up the extension in your Dynatrace environment and discovers all its **feature sets**, **metric keys**, and each metric's **dimensions**
2. Presents an interactive **checkbox list** of every metric
3. For each selected metric, asks you to choose a **detection model**, **alert direction**, and which **dimension(s) to split by**
4. Creates the corresponding **`builtin:davis.anomaly-detectors`** settings objects (DQL-based Davis Anomaly Detection) via the Settings 2.0 API

> **SaaS only** — the DQL-based Davis Anomaly Detection app is not available on Dynatrace Managed.

## Installation

```bash
pip install -e .
```

Requires Python 3.10+.

## First-run setup

On the first run the tool will prompt you for your OAuth credentials and store them at `~/.dynatrace/extensions/OAuth.json` (file mode `0600`):

```
Client ID:        dt0s02.XXXXXXXXXX
Client Secret:    ••••••••••••••••••
Resource:         urn:dtaccount:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
Environment URL:  https://<env-id>.live.dynatrace.com
```

- **Client ID / Client Secret** — from your Dynatrace account under *Access tokens → OAuth clients*
- **Resource** — your account URN, e.g. `urn:dtaccount:12345678-...`
- **Environment URL** — your SaaS environment base URL

The OAuth client needs these scopes (assign them when creating the client under *Account Management → Identity & access management → OAuth clients*):

- `settings:schemas:read` — read the anomaly-detectors schema
- `settings:objects:read` — read existing settings objects
- `settings:objects:write` — create the anomaly detectors
- `environment-api:extensions:read` — read installed extensions and download `extension.yaml`
- `storage:metrics:read` — required because each detector evaluates a DQL `timeseries` query over metrics

> **400 on token request?** Dynatrace SSO rejects the **entire** token request with `400` if *any* requested scope is invalid or was not granted to the client. The tool degrades gracefully: if the full set is rejected it retries with the three `settings:*` scopes only (and warns that extension discovery won't work). Use `--scopes "..."` to override the requested set.

> **Note:** `/api/v2/extensions` is the *classic* Environment API, so it uses the `environment-api:extensions:read` scope — **not** the platform `extensions:definitions:read` scope.

The metric keys and their feature-set grouping are read from the extension's `extension.yaml`, which the tool downloads from your environment. (Scraping the public docs site is not viable — `docs.dynatrace.com` returns HTTP 403 to automated requests.)

## Usage

```bash
# Interactive (default)
dynatrace-extension-alert-config --name "Meraki Extension"

# The name is flexible — casing and the word "extension" are ignored
dynatrace-extension-alert-config --name meraki
dynatrace-extension-alert-config --name "MERAKI extension"

# Target a specific environment by ID (overrides the stored environmentUrl)
dynatrace-extension-alert-config --name meraki --env-id abc12345

# Preview JSON payloads without making any API calls
dynatrace-extension-alert-config --name meraki --dry-run

# Non-interactive: Auto-Adaptive / Above for every metric
dynatrace-extension-alert-config --name meraki --yes

# Re-enter credentials
dynatrace-extension-alert-config --name meraki --reconfigure
```

### Flags

| Flag | Effect |
|---|---|
| `--name` | Extension display name — fuzzy-matched, casing and the word "extension" are ignored |
| `--env-id` | Dynatrace environment ID (e.g. `abc12345`). Constructs `https://<env-id>.live.dynatrace.com` and overrides the stored `environmentUrl` for this run only. |
| `--scopes` | Override the OAuth scopes requested (space-separated). Defaults to the three `settings:*` scopes. |
| `--reconfigure` | Re-enter and re-save OAuth credentials |
| `--dry-run` | Print JSON payloads, no API calls made |
| `--yes` | Non-interactive: create Auto-Adaptive / Above detectors for every metric |

### Interactive flow

```
┌─────────────────────────────────────────────────────────────┐
│  Extension: Meraki (v2.3.1)                                 │
├────────────────────┬──────────────────────────────┬─────────┤
│ Feature Set        │ Metric Key                   │ Name    │
├────────────────────┼──────────────────────────────┼─────────┤
│ device-cpu         │ meraki.device.cpu_usage      │ ...     │
│ device-memory      │ meraki.device.memory_used    │ ...     │
│ …                  │ …                            │ …       │
└────────────────────┴──────────────────────────────┴─────────┘

Select metrics (Space = toggle, Enter = confirm):
  ── device-cpu ──
  ❯ ◉ meraki.device.cpu_usage  (Meraki Appliance CPU Usage)
  ── device-memory ──
    ◯ meraki.device.memory_used
    …

Configuring meraki.device.cpu_usage:
  Detection model:  ❯ Auto-Adaptive Baseline
                      Seasonal Baseline
                      Static Threshold

  Alert when metric goes:  ❯ Above threshold
                             Below threshold
```

### Detection models

| Model | Description |
|---|---|
| **Auto-Adaptive Baseline** | Davis learns the normal range automatically. No threshold value needed. |
| **Seasonal Baseline** | Like Auto-Adaptive but accounts for time-of-day / day-of-week seasonality. |
| **Static Threshold** | Alert when the metric crosses a fixed numeric value you provide. |

For all models you choose **Above** or **Below** the threshold/baseline, then which metric **dimension(s) to split by** (or none).

## What gets created

Each selected metric becomes one `builtin:davis.anomaly-detectors` settings object. The detector evaluates a DQL `timeseries` query (`interval: 1m` is mandatory), optionally split by the dimensions you chose:

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "environment",
  "value": {
    "enabled": true,
    "title": "Meraki - Meraki Appliance CPU Usage",
    "description": "Auto-created for Meraki metric meraki.device.cpu_usage",
    "source": "dynatrace-extension-alert-config",
    "analyzer": {
      "name": "dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer",
      "input": {
        "analyzer_input_field": [
          {"key": "query", "value": "timeseries { avg(meraki.device.cpu_usage), value.A = avg(meraki.device.cpu_usage, scalar: true) }, by: { device.name }, interval: 1m"},
          {"key": "alertCondition", "value": "ABOVE"},
          {"key": "alertOnMissingData", "value": "false"},
          {"key": "violatingSamples", "value": "3"},
          {"key": "slidingWindow", "value": "5"},
          {"key": "dealertingSamples", "value": "5"},
          {"key": "threshold", "value": "80"}
        ]
      }
    },
    "eventTemplate": {
      "title": "Meraki - Meraki Appliance CPU Usage on {dims:device.name} is {alert_condition} the threshold of {threshold}",
      "description": "The metric meraki.device.cpu_usage is {alert_condition} the threshold of {threshold}.",
      "eventType": "CUSTOM_ALERT",
      "davisMerge": true
    }
  }
}
```

- **Config name** = `value.title` → `<Extension> - <Metric Name>`
- **Event title** = `<Extension> - <Metric Name> on {dims:<dim>} is {alert_condition} the threshold of {threshold}` (the ` on …` clause is dropped when no split dimension is chosen)
- `{alert_condition}`, `{threshold}`, and `{dims:<dim>}` are Dynatrace event-template placeholders resolved at event-fire time
- Baseline analyzers (auto-adaptive / seasonal) omit the `threshold` input

Verify after the run in the **Davis Anomaly Detection** app, or via API:

```bash
GET /api/v2/settings/objects?schemaIds=builtin:davis.anomaly-detectors
```

## How the extension is resolved

**Primary — environment API**: The tool lists all installed extensions in your environment and fuzzy-matches your input against their names. It then downloads the extension package and parses `extension.yaml` to read feature sets, metric keys, and each metric's dimensions (metadata + inherited group/subgroup dimensions).

**Fallback — docs scraping**: only a last resort; `docs.dynatrace.com` returns HTTP 403 to automated requests, so it is unreliable.

## Credentials file

`~/.dynatrace/extensions/OAuth.json`

```json
{
  "clientId": "dt0s02.XXXXXXXXXX",
  "clientSecret": "...",
  "resource": "urn:dtaccount:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "environmentUrl": "https://<env-id>.live.dynatrace.com"
}
```

The file is written with mode `0600` (owner read/write only). The token is fetched fresh on each run (valid 5 minutes, cached in-process).

## Notes

- **SaaS only** — this tool uses the `sso.dynatrace.com` OAuth flow, which is not available on Dynatrace Managed.
- Detection defaults: `avg()` aggregation, sliding window of 5 samples, 3 violating samples to raise, 5 to clear. These are sensible starting points; tune them in the Davis Anomaly Detection app after creation if needed.
