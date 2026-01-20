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
    channel : str
        Name of the image layer the spots were derived from.
    count_within_segmentation : bool
        Whether counts are restricted to a segmentation labels layer.
    segmentation_label : str
        Labels layer used for segmentation-restricted counting.
    rois : list of ROIConfig
        ROI entries applied to this feature.
    """

    labels: str = ""
    channel: str = ""
    count_within_segmentation: bool = False
    segmentation_label: str = ""
    rois: list[ROIConfig] = field(default_factory=list)
