"""Tests for spots feature export logic.

Notes
-----
Builds a minimal viewer with labels and image data to validate spots
export outputs.
"""

from __future__ import annotations

import csv
import json
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


def test_export_spots_writes_settings_and_masks(tmp_path: Path) -> None:
    """Write mask arrays and unified settings bundle for spots export."""
    cell_labels = np.array([[0, 1], [0, 2]], dtype=np.int32)
    spot_labels = np.array([[0, 1], [0, 0]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    viewer = DummyViewer(
        [
            Labels(
                cell_labels,
                "cells",
                metadata={
                    "task": "nuclear",
                    "run_history": [
                        {
                            "timestamp": "2026-02-06T00:00:00.000Z",
                            "task": "nuclear",
                            "runner_type": "segmentation_model",
                            "runner_name": "default_2d",
                            "settings": {"threshold": 0.3},
                        }
                    ],
                },
            ),
            Labels(
                spot_labels,
                "spots",
                metadata={
                    "task": "spots",
                    "run_history": [
                        {
                            "timestamp": "2026-02-06T01:00:00.000Z",
                            "task": "spots",
                            "runner_type": "spot_detector",
                            "runner_name": "ufish",
                            "settings": {"threshold": 0.4},
                        }
                    ],
                },
            ),
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

    settings_paths = [path for path in outputs if path.name == "feature_settings.json"]
    mask_paths = [path for path in outputs if path.name.endswith("_mask.npy")]
    assert settings_paths
    assert len(mask_paths) >= 2

    payload = json.loads(settings_paths[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "senoquant.settings"
    assert payload["feature_settings"]["feature_type"] == "Spots"
    roles = {item["role"] for item in payload["segmentation_runs"]}
    assert {"cell_segmentation", "spots_segmentation"} <= roles


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


def test_export_spots_without_segmentation_still_writes_spots(
    tmp_path: Path,
) -> None:
    """Export all spots even when no cell segmentation is configured."""
    spot_labels = np.array([[1, 0], [0, 2]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    viewer = DummyViewer(
        [
            Labels(spot_labels, "spots"),
            Image(image, "chan1"),
        ]
    )
    data = SpotsFeatureData(
        segmentations=[],
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
    csv_paths = [path for path in outputs if path.suffix == ".csv"]
    assert any(path.name == "all_spots.csv" for path in csv_paths)
    assert all(not path.name.endswith("_cells.csv") for path in csv_paths)

    spot_path = next(path for path in csv_paths if path.name == "all_spots.csv")
    with spot_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert {row["spot_id"] for row in rows} == {"1", "2"}
    assert "within_segmentation" not in rows[0]


def test_export_spots_marks_outside_segmentation_rows(tmp_path: Path) -> None:
    """Keep outside spots and annotate them with within_segmentation."""
    cell_labels = np.array(
        [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
        dtype=np.int32,
    )
    spot_labels = np.array(
        [[2, 0, 0], [0, 1, 0], [0, 0, 0]],
        dtype=np.int32,
    )
    image = np.array(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]],
        dtype=np.float32,
    )

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
    spot_path = next(path for path in outputs if path.name == "cells_spots.csv")
    with spot_path.open("r", encoding="utf-8", newline="") as handle:
        spot_rows = list(csv.DictReader(handle))
    by_id = {row["spot_id"]: row for row in spot_rows}
    assert {row["spot_id"] for row in spot_rows} == {"1", "2"}
    assert by_id["1"]["within_segmentation"] == "1"
    assert by_id["2"]["within_segmentation"] == "0"
    assert by_id["1"]["cell_id"] == "1"
    assert by_id["2"]["cell_id"] == "0"

    cell_path = next(path for path in outputs if path.name == "cells_cells.csv")
    with cell_path.open("r", encoding="utf-8", newline="") as handle:
        cell_rows = list(csv.DictReader(handle))
    assert len(cell_rows) == 1
    assert cell_rows[0]["ch1_spot_count"] == "1"


def test_export_spots_colocalization_keeps_outside_spots(tmp_path: Path) -> None:
    """Preserve outside-spot rows needed by colocalization references."""
    cell_labels = np.array(
        [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
        dtype=np.int32,
    )
    spot_a = np.array(
        [[2, 2, 0], [0, 1, 0], [0, 0, 0]],
        dtype=np.int32,
    )
    spot_b = np.array(
        [[5, 0, 0], [0, 6, 0], [0, 0, 0]],
        dtype=np.int32,
    )
    image_a = np.ones((3, 3), dtype=np.float32)
    image_b = np.ones((3, 3), dtype=np.float32)

    viewer = DummyViewer(
        [
            Labels(cell_labels, "cells"),
            Labels(spot_a, "spots_a"),
            Labels(spot_b, "spots_b"),
            Image(image_a, "chan_a"),
            Image(image_b, "chan_b"),
        ]
    )
    data = SpotsFeatureData(
        segmentations=[SpotsSegmentationConfig(label="cells")],
        channels=[
            SpotsChannelConfig(
                name="A",
                channel="chan_a",
                spots_segmentation="spots_a",
            ),
            SpotsChannelConfig(
                name="B",
                channel="chan_b",
                spots_segmentation="spots_b",
            ),
        ],
        export_colocalization=True,
    )
    feature = FeatureConfig(name="Spots", type_name="Spots", data=data)

    outputs = list(export_spots(feature, tmp_path, viewer=viewer, export_format="csv"))
    spot_path = next(path for path in outputs if path.name == "cells_spots.csv")
    with spot_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_key = {(row["channel"], row["spot_id"]): row for row in rows}
    assert by_key[("A", "2")]["within_segmentation"] == "0"
    assert by_key[("B", "5")]["within_segmentation"] == "0"
    assert by_key[("A", "2")]["colocalizes_with"] == "B:5"
    assert by_key[("B", "5")]["colocalizes_with"] == "A:2"
