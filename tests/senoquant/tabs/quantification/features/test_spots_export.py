"""Tests for spots feature export logic.

Notes
-----
Builds a minimal viewer with labels and image data to validate spots
export outputs.
"""

from __future__ import annotations

import csv
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


def test_export_spots_cells_add_cross_segmentation_overlap_column(
    tmp_path: Path,
) -> None:
    """Cells tables include overlaps_with for multiple segmentations."""
    nuclear = np.array(
        [[1, 1, 0], [0, 2, 2]],
        dtype=np.int32,
    )
    cytoplasmic = np.array(
        [[10, 10, 20], [0, 0, 20]],
        dtype=np.int32,
    )
    spots = np.array(
        [[1, 1, 2], [0, 0, 2]],
        dtype=np.int32,
    )
    image = np.array(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
        dtype=np.float32,
    )

    viewer = DummyViewer(
        [
            Labels(nuclear, "nuclear"),
            Labels(cytoplasmic, "cytoplasmic"),
            Labels(spots, "spots"),
            Image(image, "chan1"),
        ]
    )

    data = SpotsFeatureData(
        segmentations=[
            SpotsSegmentationConfig(label="nuclear"),
            SpotsSegmentationConfig(label="cytoplasmic"),
        ],
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
    cell_tables = {
        path.stem: path
        for path in outputs
        if path.suffix == ".csv" and path.stem.endswith("_cells")
    }
    assert "nuclear_cells" in cell_tables
    assert "cytoplasmic_cells" in cell_tables

    with cell_tables["nuclear_cells"].open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        nuclear_rows = list(csv.DictReader(handle))
    with cell_tables["cytoplasmic_cells"].open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        cytoplasmic_rows = list(csv.DictReader(handle))

    assert nuclear_rows and cytoplasmic_rows
    assert all("overlaps_with" in row for row in nuclear_rows)
    assert all("overlaps_with" in row for row in cytoplasmic_rows)

    nuclear_by_label = {
        row["label_id"]: row["overlaps_with"] for row in nuclear_rows
    }
    cytoplasmic_by_label = {
        row["label_id"]: row["overlaps_with"] for row in cytoplasmic_rows
    }
    assert nuclear_by_label["1"] == "cytoplasmic_10"
    assert nuclear_by_label["2"] == "cytoplasmic_20"
    assert cytoplasmic_by_label["10"] == "nuclear_1"
    assert cytoplasmic_by_label["20"] == "nuclear_2"
