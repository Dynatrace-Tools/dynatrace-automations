from __future__ import annotations

import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .models import ExtensionInfo, FeatureSet, Metric

DOCS_BASE = "https://docs.dynatrace.com/docs/observe/infrastructure-observability/extensions"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def slugify(name: str) -> str:
    """Convert an extension display name to its docs URL slug.

    'Meraki Extension' -> 'meraki'
    'Microsoft 365, Office 365' -> 'microsoft-365-office-365'
    """
    name = name.lower()
    # Remove trailing/leading " extension"
    name = re.sub(r"\bextension\b", "", name)
    # Replace non-alphanumeric sequences (spaces, commas, slashes, dots) with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", name)
    # Collapse and strip leading/trailing hyphens
    name = name.strip("-")
    return name


def fetch_docs_page(slug: str) -> Optional[str]:
    url = f"{DOCS_BASE}/{slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException:
        pass
    return None


def parse_feature_sets(html: str, extension_name: str = "unknown") -> ExtensionInfo:
    """Parse the Dynatrace docs page HTML to extract feature sets and their metrics."""
    soup = BeautifulSoup(html, "lxml")
    feature_sets: list[FeatureSet] = []
    current_fs: Optional[FeatureSet] = None

    # Find the "Feature sets" heading to locate the right section
    fs_section = None
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        if "feature set" in heading.get_text(strip=True).lower():
            fs_section = heading
            break

    if not fs_section:
        # If no feature sets section found, return empty info
        return ExtensionInfo(name=extension_name, version="unknown", feature_sets=[])

    # Walk siblings after the feature sets heading
    for sibling in fs_section.find_next_siblings():
        tag = sibling.name
        if tag is None:
            continue

        # A heading inside the section signals a new feature set or end of section
        if re.match(r"h[1-6]", tag):
            heading_level = int(tag[1])
            fs_heading_level = int(fs_section.name[1])
            # Same or higher-level heading = end of feature sets section
            if heading_level <= fs_heading_level:
                break
            # Deeper heading = feature set name
            fs_name = sibling.get_text(strip=True)
            current_fs = FeatureSet(name=fs_name)
            feature_sets.append(current_fs)
            continue

        # Look for metric tables inside this section
        if tag == "table" and current_fs is not None:
            metrics = _parse_metric_table(sibling)
            current_fs.metrics.extend(metrics)

    return ExtensionInfo(
        name=extension_name,
        version="unknown",
        feature_sets=feature_sets,
    )


def _parse_metric_table(table) -> list[Metric]:
    metrics: list[Metric] = []
    rows = table.find_all("tr")
    if not rows:
        return metrics

    # Detect columns from the header row
    header_row = rows[0]
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    name_col = _find_col(headers, ["metric name", "name"])
    key_col = _find_col(headers, ["metric key", "key"])
    desc_col = _find_col(headers, ["description", "desc"])

    if key_col is None:
        return metrics

    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) <= key_col:
            continue
        key = cells[key_col].get_text(strip=True)
        if not key or key == "—":
            continue
        name = cells[name_col].get_text(strip=True) if name_col is not None and name_col < len(cells) else key
        if name == "—":
            name = key
        desc = cells[desc_col].get_text(strip=True) if desc_col is not None and desc_col < len(cells) else ""
        if desc == "—":
            desc = ""
        metrics.append(Metric(key=key, name=name, description=desc))
    return metrics


def _find_col(headers: list[str], candidates: list[str]) -> Optional[int]:
    for candidate in candidates:
        for i, h in enumerate(headers):
            if candidate in h:
                return i
    return None


def scrape_extension(name: str) -> Optional[ExtensionInfo]:
    slug = slugify(name)
    html = fetch_docs_page(slug)
    if not html:
        return None
    return parse_feature_sets(html, extension_name=name)
