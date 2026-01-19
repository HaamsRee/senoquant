"""Dataclass-based configuration models for quantification features."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Type
import uuid


class FeatureData:
    """Base class for feature-specific configuration data."""


@dataclass
class ROIConfig:
    """Configuration for a single ROI entry."""

    name: str = ""
    layer: str = ""
    roi_type: str = "Include"


@dataclass
class MarkerSegmentationConfig:
    """Configuration for a segmentation labels entry."""

    label: str = ""


@dataclass
class MarkerChannelConfig:
    """Configuration for a marker channel entry."""

    name: str = ""
    channel: str = ""
    threshold_enabled: bool = False
    threshold_method: str = "Otsu"
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None


@dataclass
class MarkerFeatureData(FeatureData):
    """Configuration for marker feature inputs."""

    segmentations: list[MarkerSegmentationConfig] = field(default_factory=list)
    channels: list[MarkerChannelConfig] = field(default_factory=list)
    rois: list[ROIConfig] = field(default_factory=list)


@dataclass
class SpotsFeatureData(FeatureData):
    """Configuration for spots feature inputs."""

    labels: str = ""
    rois: list[ROIConfig] = field(default_factory=list)


@dataclass
class ColocalizationFeatureData(FeatureData):
    """Configuration for colocalization feature inputs."""

    labels_a_id: Optional[str] = None
    labels_b_id: Optional[str] = None


@dataclass
class FeatureConfig:
    """Configuration for a single quantification feature."""

    feature_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    type_name: str = ""
    data: FeatureData = field(default_factory=FeatureData)


FEATURE_DATA_FACTORY: dict[str, Type[FeatureData]] = {
    "Marker": MarkerFeatureData,
    "Spots": SpotsFeatureData,
    "Colocalization": ColocalizationFeatureData,
}


def build_feature_data(feature_type: str) -> FeatureData:
    """Create a feature data instance for the specified feature type.

    Parameters
    ----------
    feature_type : str
        Feature type name.

    Returns
    -------
    FeatureData
        Feature-specific configuration instance.
    """
    data_cls = FEATURE_DATA_FACTORY.get(feature_type, FeatureData)
    return data_cls()

