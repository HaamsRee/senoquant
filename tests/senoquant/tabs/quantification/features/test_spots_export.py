"""Tests for spots feature export logic.

Notes
-----
Builds a minimal viewer with labels and image data to validate spots
export outputs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.base import FeatureConfig
from senoquant.tabs.quantification.features.spots.config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)
from senoquant.tabs.quantification.features.spots.export import export_spots


def test_export_spots_csv(tmp_path: Path) -> None:
    """Export spots data to CSV.

    Returns
    -------
    None
    """
    cell_labels = np.array([[0, 1], [0, 2]], dtype=np.int32)
    spot_labels = np.array([[0, 1], [0, 0]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    viewer = DummyViewer(
        [
            Labels(cell_labels, "cells"),
            Labels(spot_labels, "spots"),
            Image(image, "chan1"),
        ]
    )

    data = SpotsFeatureData(
        segmentations=[SpotsSegmentationConfig(label="cells")],
        channels=[
            SpotsChannelConfig(
                name="Ch1",
                channel="chan1",
                spots_segmentation="spots",
            )
        ],
    )
    feature = FeatureConfig(name="Spots", type_name="Spots", data=data)

    outputs = list(export_spots(feature, tmp_path, viewer=viewer, export_format="csv"))
    assert any(path.suffix == ".csv" for path in outputs)
    assert all(path.exists() for path in outputs)
