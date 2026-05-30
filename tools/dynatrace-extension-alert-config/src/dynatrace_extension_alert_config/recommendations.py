"""Recommend a sensible static-threshold default from a metric's unit.

Dynatrace extension metrics declare a ``unit`` in their ``extension.yaml``
metadata (e.g. ``Percent``, ``Ratio``, ``MilliSecond``). For bounded units we
can suggest a reasonable starting threshold without any AI — a percentage metric
like CPU usage is always 0-100, so "alert above 80%" is a defensible default the
user can accept or override.

This is intentionally conservative: it only suggests for units whose range and
meaning are unambiguous, and returns ``None`` otherwise (the user then types a
value with no pre-fill).
"""
from __future__ import annotations
from typing import Optional

# Dynatrace unit identifiers that represent a 0-100 percentage.
_PERCENT_UNITS = {"percent", "percentage", "percent(0-100)", "%"}
# Units that represent a 0-1 ratio.
_RATIO_UNITS = {"ratio", "ratio(0-1)", "ratio (0-1)"}

# Above-direction is the common "too high" case (usage/saturation); below-
# direction is the "too low" case (free capacity / availability dropping).
_PERCENT_ABOVE = 80.0
_PERCENT_BELOW = 20.0
_RATIO_ABOVE = 0.8
_RATIO_BELOW = 0.2


def _normalize_unit(unit: str) -> str:
    return "".join((unit or "").lower().split())


def recommend_threshold(unit: str, direction: str) -> Optional[float]:
    """Suggest a static threshold for a unit + alert direction, or None.

    direction is ``"ABOVE"`` or ``"BELOW"``.
    """
    u = _normalize_unit(unit)
    if u in _PERCENT_UNITS:
        return _PERCENT_ABOVE if direction == "ABOVE" else _PERCENT_BELOW
    if u in _RATIO_UNITS:
        return _RATIO_ABOVE if direction == "ABOVE" else _RATIO_BELOW
    return None


def format_number(value: float) -> str:
    """Render a number without a trailing ``.0`` for integers."""
    return str(int(value)) if float(value).is_integer() else str(value)
