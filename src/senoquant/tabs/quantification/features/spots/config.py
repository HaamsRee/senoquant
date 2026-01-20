"""Spots feature configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..base import FeatureData
from ..roi import ROIConfig


@dataclass
class SpotsFeatureData(FeatureData):
    """Configuration for spots feature inputs.

    Attributes
    ----------
    labels : str
        Name of the labels layer containing spot detections.
    rois : list of ROIConfig
        ROI entries applied to this feature.
    """

    labels: str = ""
    rois: list[ROIConfig] = field(default_factory=list)
