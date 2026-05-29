# dynatrace-extension-alert-config

Create [Davis Anomaly Detection](https://docs.dynatrace.com/docs/discover-dynatrace/platform/davis-ai/anomaly-detection/metric-events) configurations for every metric in any Dynatrace extension — interactively, from the CLI.

## What it does

Given an extension name (e.g. `Meraki Extension`), the tool:

1. Looks up the extension in your Dynatrace environment and discovers all its **feature sets** and **metric keys**
2. Presents an interactive **checkbox list** of every metric
3. For each selected metric, asks you to choose a **detection model** and **alert direction**
4. Creates the corresponding `builtin:anomaly-detection.metric-events` settings objects via the Settings 2.0 API

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

The OAuth client needs these scopes: `settings:objects:read`, `settings:objects:write`, `settings:schemas:read`, `extensions:read`, `extensions.environment:read`.

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

For all models you choose **Above** or **Below** the threshold/baseline.

## What gets created

Each selected metric becomes one `builtin:anomaly-detection.metric-events` settings object:

```json
{
  "schemaId": "builtin:anomaly-detection.metric-events",
  "scope": "environment",
  "value": {
    "enabled": true,
    "summary": "Meraki – meraki.device.cpu_usage anomaly detection",
    "queryDefinition": {
      "type": "METRIC_KEY",
      "metricKey": "meraki.device.cpu_usage",
      "aggregation": "AVG"
    },
    "modelProperties": {
      "type": "AUTO_ADAPTIVE_BASELINE",
      "alertCondition": "ABOVE",
      "violatingSamples": 3,
      "slidingWindow": 5,
      "dealertingSamples": 5,
      "numberOfSignalFluctuations": 1.0
    },
    "eventTemplate": {
      "title": "CPU Usage collected for the top MX devices is {alert_condition} the threshold of {threshold}",
      "description": "The metric meraki.device.cpu_usage is {alert_condition} the threshold of {threshold}.",
      "eventType": "CUSTOM_ALERT",
      "davisMerge": true
    }
  }
}
```

`{alert_condition}` and `{threshold}` are Dynatrace event-template placeholders resolved at event-fire time.

Verify after the run:

```
Settings → Anomaly Detection → Metric events
```

or via API:

```bash
GET /api/v2/settings/objects?schemaIds=builtin:anomaly-detection.metric-events
```

## How the extension is resolved

**Primary — environment API**: The tool lists all installed extensions in your environment and fuzzy-matches your input against their names. It then fetches the active extension definition to read feature sets and metric keys.

**Fallback — docs scraping**: If the extension isn't found in the environment (e.g. not yet installed), the tool scrapes the Dynatrace documentation page for that extension, parsing the *Feature sets* section and metric tables.

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
- Detection defaults: `AVG` aggregation, sliding window of 5 samples, 3 violating samples to raise, 5 to clear. These are sensible starting points; tune them in Settings → Metric events after creation if needed.
