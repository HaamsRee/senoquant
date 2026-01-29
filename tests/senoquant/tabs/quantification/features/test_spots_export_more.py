"""Additional tests for spots export helpers."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.spots import export as spots_export


class DummyChannel:
    """Simple channel config stub."""

    def __init__(self, name: str, channel: str, spots_segmentation: str) -> None:
        self.name = name
        self.channel = channel
        self.spots_segmentation = spots_segmentation


class DummyROI:
    """Simple ROI config stub."""

    def __init__(self, name: str, layer: str, roi_type: str = "Include") -> None:
        self.name = name
        self.layer = layer
        self.roi_type = roi_type


class Shapes:
    """Shapes layer stub for ROI masks."""

    def __init__(self, name: str, mask: np.ndarray) -> None:
        self.name = name
        self._mask = np.asarray(mask)

    def to_masks(self, mask_shape=None):
        """Return a stored mask regardless of shape."""
        return self._mask


def test_build_channel_entries_filters_channels() -> None:
    """Filter missing and mismatched channels.

    Returns
    -------
    None
    """
    cell_labels = np.zeros((2, 2), dtype=np.int32)
    spots_ok = np.array([[1, 0], [0, 0]], dtype=np.int32)
    spots_bad = np.zeros((3, 3), dtype=np.int32)
    viewer = DummyViewer(
        [
            Labels(cell_labels, "cells"),
            Labels(spots_ok, "spots_ok"),
            Labels(spots_bad, "spots_bad"),
            Image(np.ones((2, 2), dtype=np.float32), "img"),
        ]
    )
    channels = [
        DummyChannel("A", "img", "spots_ok"),
        DummyChannel("Missing", "img", "missing"),
        DummyChannel("Bad", "img", "spots_bad"),
    ]
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        entries = spots_export._build_channel_entries(
            viewer, channels, cell_labels.shape, "cells"
        )
    assert len(entries) == 1
    assert entries[0]["channel_label"] == "A"
    assert any("not found" in str(item.message) for item in captured)
    assert any("shape mismatch" in str(item.message) for item in captured)


def test_append_channel_exports_no_spots() -> None:
    """Handle channels without spot labels.

    Returns
    -------
    None
    """
    cell_labels = np.array([[0, 1], [2, 2]], dtype=np.int32)
    cell_ids, centroids = spots_export._compute_centroids(cell_labels)
    cell_rows = spots_export._initialize_rows(cell_ids, centroids, None)
    entry = {
        "channel_label": "Ch 1",
        "channel_layer": None,
        "spots_labels": np.zeros_like(cell_labels),
    }
    cell_header: list[str] = []
    spot_rows: list[dict[str, object]] = []
    spot_header: list[str] = []
    spot_lookup: dict[tuple[int, int], dict[str, object]] = {}

    spots_export._append_channel_exports(
        0,
        entry,
        cell_labels,
        cell_ids,
        cell_header,
        cell_rows,
        spot_rows,
        spot_header,
        spot_lookup,
        None,
        [],
    )

    assert "ch_1_spot_count" in cell_header
    assert spot_rows == []
    assert cell_rows[0]["ch_1_spot_count"] == 0
    assert np.isnan(cell_rows[0]["ch_1_spot_mean_intensity"])


def test_append_channel_exports_warns_on_mismatch() -> None:
    """Warn on mismatched image/spot shapes.

    Returns
    -------
    None
    """
    cell_labels = np.array([[1, 1], [0, 0]], dtype=np.int32)
    cell_ids, centroids = spots_export._compute_centroids(cell_labels)
    cell_rows = spots_export._initialize_rows(cell_ids, centroids, None)
    entry = {
        "channel_label": "Chan",
        "channel_layer": Image(np.ones((3, 3), dtype=np.float32), "img"),
        "spots_labels": np.array([[1, 0], [0, 0]], dtype=np.int32),
    }
    cell_header: list[str] = []
    spot_rows: list[dict[str, object]] = []
    spot_header: list[str] = []
    spot_lookup: dict[tuple[int, int], dict[str, object]] = {}

    with pytest.warns(RuntimeWarning):
        spots_export._append_channel_exports(
            0,
            entry,
            cell_labels,
            cell_ids,
            cell_header,
            cell_rows,
            spot_rows,
            spot_header,
            spot_lookup,
            None,
            [],
        )

    assert spot_rows
    assert "spot_mean_intensity" in spot_rows[0]
    assert np.isnan(spot_rows[0]["spot_mean_intensity"])


def test_colocalization_columns_and_counts() -> None:
    """Add colocalization columns for overlapping spots.

    Returns
    -------
    None
    """
    labels_a = np.array([[1, 0], [0, 0]], dtype=np.int32)
    labels_b = np.array([[2, 0], [0, 0]], dtype=np.int32)
    channel_entries = [
        {"spots_labels": labels_a, "channel_label": "A"},
        {"spots_labels": labels_b, "channel_label": "B"},
    ]
    adjacency = spots_export._build_colocalization_adjacency(channel_entries)
    spot_rows = [
        {"spot_id": 1, "cell_id": 1, "channel": "A"},
        {"spot_id": 2, "cell_id": 1, "channel": "B"},
    ]
    spot_lookup = {
        (0, 1): {"row": spot_rows[0], "cell_id": 1},
        (1, 2): {"row": spot_rows[1], "cell_id": 1},
    }
    cell_rows = [{"label_id": 1}]
    cell_ids = np.array([1], dtype=int)
    cell_header: list[str] = []

    spots_export._apply_colocalization_columns(
        cell_rows,
        cell_ids,
        cell_header,
        spot_rows,
        spot_lookup,
        adjacency,
        channel_entries,
        max_cell_id=1,
    )

    assert cell_rows[0]["colocalization_event_count"] == 1
    assert spot_rows[0]["colocalizes_with"] == "B:2"
    assert spot_rows[1]["colocalizes_with"] == "A:1"


def test_spot_roi_columns_and_values() -> None:
    """Compute ROI columns and spot membership values.

    Returns
    -------
    None
    """
    mask = np.array([[True, False], [False, True]])
    viewer = DummyViewer([Shapes("roi", mask)])
    rois = [DummyROI("My ROI", "roi", roi_type="Exclude")]
    columns = spots_export._spot_roi_columns(viewer, rois, "cells", mask.shape)
    assert columns[0][0] == "excluded_from_roi_my_roi"
    centroids = np.array([[0, 0], [1, 1]], dtype=float)
    values = spots_export._spot_roi_values(centroids, columns)
    assert values[0][1].tolist() == [1, 1]


def test_spot_header_and_rows(tmp_path: Path) -> None:
    """Build spot headers and rows with physical units.

    Returns
    -------
    None
    """
    mask = np.array([[True, False], [False, True]])
    roi_columns = [("included_in_roi_r1", mask)]
    pixel_sizes = np.array([2.0, 3.0], dtype=float)
    header = spots_export._spot_header(2, pixel_sizes, roi_columns)
    assert "centroid_y_um" in header
    assert "spot_area_um2" in header
    rows = spots_export._spot_rows(
        np.array([1]),
        np.array([2]),
        np.array([[1.0, 0.0]]),
        np.array([4.0]),
        np.array([5.0]),
        "Chan",
        pixel_sizes,
        roi_columns,
    )
    assert rows[0]["spot_area_um2"] == 24.0

    output = tmp_path / "spots.csv"
    spots_export._write_table(output, header, rows, "csv")
    assert output.exists()
