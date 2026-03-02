"""Additional tests for marker export helpers."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.quantification.features.marker import export as marker_export
from senoquant.tabs.quantification.features.marker.config import MarkerChannelConfig


class DummyROI:
    """Simple ROI config stub."""

    def __init__(self, name: str, layer: str, roi_type: str = "Include") -> None:
        self.name = name
        self.layer = layer
        self.roi_type = roi_type


class Shapes:
    """Shapes layer stub for ROI geometry."""

    def __init__(
        self,
        name: str,
        data: np.ndarray | list[np.ndarray],
        shape_type: str = "polygon",
    ) -> None:
        self.name = name
        if isinstance(data, list):
            self.data = [np.asarray(item, dtype=float) for item in data]
        else:
            self.data = [np.asarray(data, dtype=float)]
        self.shape_type = [shape_type] * len(self.data)


def test_pixel_sizes_missing_metadata() -> None:
    """Return None when metadata is incomplete.

    Returns
    -------
    None
    """
    layer = Image(np.zeros((2, 2)), "img", metadata=None)
    assert marker_export._pixel_sizes(layer, 2) is None
    assert marker_export._pixel_sizes_from_metadata(1.0, None, 2.0, 2) is None
    assert marker_export._pixel_sizes_from_metadata(1.0, 2.0, 3.0, 4) is None
    assert marker_export._axis_names(4) == [
        "axis_0",
        "axis_1",
        "axis_2",
        "axis_3",
    ]


def test_pixel_volume_and_threshold_disabled() -> None:
    """Compute pixel volume and skip thresholds when disabled.

    Returns
    -------
    None
    """
    layer = Image(
        np.zeros((2, 2)),
        "img",
        metadata={"physical_pixel_sizes": {"X": "2.0", "Y": 3.0, "Z": 4.0}},
    )
    assert marker_export._pixel_volume(layer, 2) == 6.0
    channel = MarkerChannelConfig(name="Ch", channel="img", threshold_enabled=False)
    mean = np.array([1.0, 2.0], dtype=float)
    raw = np.array([3.0, 4.0], dtype=float)
    integ = np.array([5.0, 6.0], dtype=float)
    t_mean, t_raw, t_integ = marker_export._apply_threshold(
        mean, raw, integ, channel
    )
    assert np.allclose(t_mean, mean)
    assert np.allclose(t_raw, raw)
    assert np.allclose(t_integ, integ)


def test_add_roi_columns_and_masks() -> None:
    """Add ROI membership columns for include/exclude ROIs.

    Returns
    -------
    None
    """
    labels = np.array([[0, 1], [0, 0]], dtype=np.int32)
    label_ids, centroids = marker_export._compute_centroids(labels)
    rows = marker_export._initialize_rows(label_ids, centroids, None)
    polygon = np.array(
        [
            [-0.5, 0.5],
            [-0.5, 1.5],
            [0.5, 1.5],
            [0.5, 0.5],
        ],
        dtype=float,
    )
    viewer = DummyViewer([Shapes("roi", polygon)])
    rois = [DummyROI("My ROI", "roi", roi_type="Exclude")]

    marker_export._add_roi_columns(rows, centroids, viewer, rois, "cells")
    assert rows[0]["excluded_from_roi_my_roi"] == 1


def test_add_roi_columns_warns_on_missing_mask() -> None:
    """Warn when ROI mask cannot be rendered.

    Returns
    -------
    None
    """
    labels = np.array([[0, 1], [0, 0]], dtype=np.int32)
    label_ids, centroids = marker_export._compute_centroids(labels)
    rows = marker_export._initialize_rows(label_ids, centroids, None)
    broken_layer = type("Shapes", (), {"name": "roi", "data": None})()
    viewer = DummyViewer([broken_layer])
    rois = [DummyROI("Bad", "roi", roi_type="Include")]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        marker_export._add_roi_columns(
            rows, centroids, viewer, rois, "cells"
        )
    assert any("could not be evaluated" in str(item.message) for item in captured)


def test_write_table_csv(tmp_path: Path) -> None:
    """Write CSV output for marker export.

    Returns
    -------
    None
    """
    header = ["label_id", "centroid_y_pixels"]
    rows = [{"label_id": 1, "centroid_y_pixels": 0.0}]
    output = tmp_path / "markers.csv"
    marker_export._write_table(output, header, rows, "csv")
    assert output.exists()


def test_add_roi_columns_3d_xy_roi_propagates_along_z() -> None:
    """Propagate an XY ROI across Z for 3D centroid membership.

    Returns
    -------
    None
    """
    labels = np.zeros((3, 3, 3), dtype=np.int32)
    labels[0, 1, 1] = 1
    labels[2, 1, 1] = 2
    label_ids, centroids = marker_export._compute_centroids(labels)
    rows = marker_export._initialize_rows(label_ids, centroids, None)
    xy_polygon = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 2.0],
            [1.0, 2.0, 2.0],
            [1.0, 2.0, 0.0],
        ],
        dtype=float,
    )
    viewer = DummyViewer([Shapes("roi", xy_polygon)])
    rois = [DummyROI("All Z", "roi", roi_type="Include")]

    marker_export._add_roi_columns(rows, centroids, viewer, rois, "cells")
    assert rows[0]["included_in_roi_all_z"] == 1
    assert rows[1]["included_in_roi_all_z"] == 1
