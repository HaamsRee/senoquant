"""Tests for marker feature export logic.

Notes
-----
Builds a minimal viewer with labels and image data to validate export
outputs.
"""

from __future__ import annotations

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
