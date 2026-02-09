"""Tests for marker feature export logic.

Notes
-----
Builds a minimal viewer with labels and image data to validate export
outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.marker.config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)
from senoquant.tabs.quantification.features.marker.export import export_marker


def test_export_marker_csv(tmp_path: Path) -> None:
    """Export marker data to CSV.

    Returns
    -------
    None
    """
    labels = np.array([[0, 1], [0, 2]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    viewer = DummyViewer(
        [
            Labels(labels, "cells"),
            Image(image, "chan1"),
        ]
    )

    data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="cells")],
        channels=[MarkerChannelConfig(name="Ch1", channel="chan1", threshold_enabled=True)],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)

    outputs = list(export_marker(feature, tmp_path, viewer=viewer, export_format="csv"))
    assert any(path.suffix == ".csv" for path in outputs)
    assert all(path.exists() for path in outputs)


def test_export_marker_writes_settings_and_masks(tmp_path: Path) -> None:
    """Write mask arrays and unified settings bundle for marker export."""
    labels = np.array([[0, 1], [0, 2]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    viewer = DummyViewer(
        [
            Labels(
                labels,
                "cells",
                metadata={
                    "task": "nuclear",
                    "run_history": [
                        {
                            "timestamp": "2026-02-06T00:00:00.000Z",
                            "task": "nuclear",
                            "runner_type": "segmentation_model",
                            "runner_name": "default_2d",
                            "settings": {"threshold": 0.2},
                        }
                    ],
                },
            ),
            Image(image, "chan1"),
        ]
    )
    data = MarkerFeatureData(
        segmentations=[MarkerSegmentationConfig(label="cells")],
        channels=[MarkerChannelConfig(name="Ch1", channel="chan1")],
    )
    feature = FeatureConfig(name="Markers", type_name="Markers", data=data)

    outputs = list(export_marker(feature, tmp_path, viewer=viewer, export_format="csv"))

    settings_paths = [path for path in outputs if path.name == "feature_settings.json"]
    mask_paths = [path for path in outputs if path.name.endswith("_mask.npy")]
    assert settings_paths
    assert mask_paths
    assert np.array_equal(np.load(mask_paths[0]), labels)
    assert not any(path.name == "marker_thresholds.json" for path in outputs)

    payload = json.loads(settings_paths[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "senoquant.settings"
    assert payload["feature_settings"]["feature_type"] == "Markers"
    assert payload["segmentation_runs"]
    assert payload["segmentation_runs"][0]["layer_name"] == "cells"
    assert payload["segmentation_runs"][0]["run_history"][0]["runner_name"] == "default_2d"
