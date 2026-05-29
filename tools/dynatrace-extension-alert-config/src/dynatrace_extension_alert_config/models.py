from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Metric:
    key: str
    name: str
    description: str = ""
    feature_set: str = "default"


@dataclass
class FeatureSet:
    name: str
    metrics: list[Metric] = field(default_factory=list)


@dataclass
class ExtensionInfo:
    name: str
    version: str
    feature_sets: list[FeatureSet] = field(default_factory=list)

    def all_metrics(self) -> list[Metric]:
        return [m for fs in self.feature_sets for m in fs.metrics]


@dataclass
class DetectorChoice:
    metric: Metric
    model: str          # AUTO_ADAPTIVE_BASELINE | SEASONAL_BASELINE | STATIC_THRESHOLD
    direction: str      # ABOVE | BELOW
    threshold: Optional[float] = None
