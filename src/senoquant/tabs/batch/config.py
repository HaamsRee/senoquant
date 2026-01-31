"""Batch job configuration and serialization helpers.

This module defines dataclasses used to capture batch settings from the UI
and persist them to JSON. The serialization format keeps feature configs
portable across sessions and mirrors the Quantification tab structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable
import json

from senoquant.tabs.quantification.features import FeatureConfig
from senoquant.tabs.quantification.features.base import FeatureData
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.spots.config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)
from senoquant.tabs.quantification.features.roi import ROIConfig


@dataclass(slots=True)
class BatchChannelConfig:
    """Channel mapping configuration.

    Attributes
    ----------
    name : str
        User-facing channel name (used in UI and exports).
    index : int
        Zero-based channel index in the input image.
    """

    name: str
    index: int


@dataclass(slots=True)
class BatchSegmentationConfig:
    """Segmentation configuration for a single task."""
    enabled: bool = False
    model: str = ""
    channel: str = ""
    settings: dict = field(default_factory=dict)


@dataclass(slots=True)
class BatchCytoplasmicConfig:
    """Cytoplasmic segmentation configuration."""
    enabled: bool = False
    model: str = ""
    channel: str = ""
    nuclear_channel: str = ""
    settings: dict = field(default_factory=dict)


@dataclass(slots=True)
class BatchSpotsConfig:
    """Spot detection configuration."""
    enabled: bool = False
    detector: str = ""
    channels: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    min_size: int = 0
    max_size: int = 0


@dataclass(slots=True)
class BatchQuantificationConfig:
    """Quantification configuration."""
    enabled: bool = False
    format: str = "xlsx"
    features: list[FeatureConfig] = field(default_factory=list)


@dataclass(slots=True)
class BatchJobConfig:
    """Top-level batch configuration.

    This structure is the single payload passed from the UI to the backend.
    It is also the serialized representation used in batch profiles.
    """
    input_path: str = ""
    output_path: str = ""
    extensions: list[str] = field(default_factory=list)
    include_subfolders: bool = False
    process_all_scenes: bool = False
    overwrite: bool = False
    output_format: str = "tif"
    channel_map: list[BatchChannelConfig] = field(default_factory=list)
    nuclear: BatchSegmentationConfig = field(default_factory=BatchSegmentationConfig)
    cytoplasmic: BatchCytoplasmicConfig = field(default_factory=BatchCytoplasmicConfig)
    spots: BatchSpotsConfig = field(default_factory=BatchSpotsConfig)
    quantification: BatchQuantificationConfig = field(default_factory=BatchQuantificationConfig)

    def to_dict(self) -> dict:
        """Serialize the job config to a JSON-friendly dictionary.

        Returns
        -------
        dict
            JSON-compatible representation of the batch config.
        """
        payload = asdict(self)
        payload["quantification"]["features"] = [
            _serialize_feature(feature)
            for feature in self.quantification.features
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "BatchJobConfig":
        """Hydrate a job config from a JSON payload.

        Parameters
        ----------
        payload : dict
            JSON-compatible representation of the batch config.

        Returns
        -------
        BatchJobConfig
            Parsed configuration instance.
        """
        channel_map = [
            BatchChannelConfig(**item)
            for item in payload.get("channel_map", [])
        ]
        nuclear = BatchSegmentationConfig(
            **payload.get("nuclear", {})
        )
        cytoplasmic = BatchCytoplasmicConfig(
            **payload.get("cytoplasmic", {})
        )
        spots = BatchSpotsConfig(
            **payload.get("spots", {})
        )
        quant_payload = payload.get("quantification", {})
        features = [
            _deserialize_feature(item)
            for item in quant_payload.get("features", [])
        ]
        quantification = BatchQuantificationConfig(
            enabled=bool(quant_payload.get("enabled", False)),
            format=quant_payload.get("format", "xlsx"),
            features=features,
        )
        return cls(
            input_path=payload.get("input_path", ""),
            output_path=payload.get("output_path", ""),
            extensions=list(payload.get("extensions", [])),
            include_subfolders=bool(payload.get("include_subfolders", False)),
            process_all_scenes=bool(payload.get("process_all_scenes", False)),
            overwrite=bool(payload.get("overwrite", False)),
            output_format=payload.get("output_format", "tif"),
            channel_map=channel_map,
            nuclear=nuclear,
            cytoplasmic=cytoplasmic,
            spots=spots,
            quantification=quantification,
        )

    def save(self, path: str) -> None:
        """Persist the configuration to disk.

        Parameters
        ----------
        path : str
            Destination file path for the JSON profile.
        """
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)

    @classmethod
    def load(cls, path: str) -> "BatchJobConfig":
        """Load a configuration from disk.

        Parameters
        ----------
        path : str
            Source JSON profile file.

        Returns
        -------
        BatchJobConfig
            Loaded configuration instance.
        """
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return cls.from_dict(payload)


def _serialize_feature(feature: FeatureConfig) -> dict:
    """Serialize a Quantification feature into a JSON payload."""
    return {
        "feature_id": feature.feature_id,
        "name": feature.name,
        "type_name": feature.type_name,
        "data": _serialize_feature_data(feature.data),
    }


def _serialize_feature_data(data_obj: object) -> dict:
    """Serialize feature-specific data payloads."""
    if isinstance(data_obj, MarkerFeatureData):
        return {
            "type": "Markers",
            "payload": asdict(data_obj),
        }
    if isinstance(data_obj, SpotsFeatureData):
        return {
            "type": "Spots",
            "payload": asdict(data_obj),
        }
    return {"type": "Unknown", "payload": {}}


def _deserialize_feature(payload: dict) -> FeatureConfig:
    """Deserialize a feature payload into a FeatureConfig."""
    feature_id = payload.get("feature_id", "")
    name = payload.get("name", "")
    type_name = payload.get("type_name", "")
    data_payload = payload.get("data", {})
    data_type = data_payload.get("type")
    data_obj = _deserialize_feature_data(data_type, data_payload.get("payload", {}))
    if feature_id:
        return FeatureConfig(
            feature_id=feature_id,
            name=name,
            type_name=type_name,
            data=data_obj,
        )
    return FeatureConfig(name=name, type_name=type_name, data=data_obj)


def _deserialize_feature_data(data_type: str, payload: dict):
    """Deserialize feature payloads into feature data objects."""
    if data_type == "Markers":
        return MarkerFeatureData(
            segmentations=[
                MarkerSegmentationConfig(**item)
                for item in payload.get("segmentations", [])
            ],
            channels=[
                MarkerChannelConfig(**item)
                for item in payload.get("channels", [])
            ],
            rois=[ROIConfig(**item) for item in payload.get("rois", [])],
        )
    if data_type == "Spots":
        return SpotsFeatureData(
            segmentations=[
                SpotsSegmentationConfig(**item)
                for item in payload.get("segmentations", [])
            ],
            channels=[
                SpotsChannelConfig(**item)
                for item in payload.get("channels", [])
            ],
            rois=[ROIConfig(**item) for item in payload.get("rois", [])],
            export_colocalization=bool(payload.get("export_colocalization", False)),
        )
    return FeatureData()
