"""Marker feature configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..base import FeatureData
from ..roi import ROIConfig


@dataclass
class MarkerSegmentationConfig:
    """Configuration for a segmentation labels entry.

    Attributes
    ----------
    label : str
        Name of the labels layer selected for this segmentation entry.
    """

    label: str = ""


@dataclass
class MarkerChannelConfig:
    """Configuration for a marker channel entry.

    Attributes
    ----------
    name : str
        User-friendly label for the channel entry.
    channel : str
        Selected image layer name.
    threshold_enabled : bool
        Whether threshold controls are active.
    threshold_method : str
        Automatic threshold method name.
    threshold_min : float or None
        Minimum threshold value.
    threshold_max : float or None
        Maximum threshold value.
    """

    name: str = ""
    channel: str = ""
    threshold_enabled: bool = False
    threshold_method: str = "Manual"
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None


@dataclass
class MarkerFeatureData(FeatureData):
    """Configuration for marker feature inputs.

    Attributes
    ----------
    segmentations : list of MarkerSegmentationConfig
        Segmentation label selections.
    channels : list of MarkerChannelConfig
        Channel configurations used for marker measurement.
    rois : list of ROIConfig
        ROI entries applied to this feature.
    """

    segmentations: list[MarkerSegmentationConfig] = field(default_factory=list)
    channels: list[MarkerChannelConfig] = field(default_factory=list)
    rois: list[ROIConfig] = field(default_factory=list)
