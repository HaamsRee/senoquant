"""Spots feature configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..base import FeatureData
from ..roi import ROIConfig


@dataclass
class SpotsSegmentationConfig:
    """Configuration for a segmentation filter entry.

    Attributes
    ----------
    label : str
        Name of the labels layer selected for this segmentation entry.
    """

    label: str = ""


@dataclass
class SpotsChannelConfig:
    """Configuration for a spots channel entry.

    Attributes
    ----------
    name : str
        User-friendly label for the channel entry.
    channel : str
        Selected image layer name.
    spots_segmentation : str
        Labels layer containing the spots segmentation for this channel.
    """

    name: str = ""
    channel: str = ""
    spots_segmentation: str = ""


@dataclass
class SpotsFeatureData(FeatureData):
    """Configuration for spots feature inputs.

    Attributes
    ----------
    segmentations : list of SpotsSegmentationConfig
        Segmentation filters applied to the full set of spots.
    channels : list of SpotsChannelConfig
        Channel configurations used for spots measurement.
    rois : list of ROIConfig
        ROI entries applied to this feature.
    export_colocalization : bool
        Whether to include colocalization columns in the export.
    """

    segmentations: list[SpotsSegmentationConfig] = field(default_factory=list)
    channels: list[SpotsChannelConfig] = field(default_factory=list)
    rois: list[ROIConfig] = field(default_factory=list)
    export_colocalization: bool = False
