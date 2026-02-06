"""Tests for marker export helper utilities."""

from __future__ import annotations

import numpy as np

from senoquant.tabs.quantification.features.marker.config import MarkerChannelConfig
from senoquant.tabs.quantification.features.marker import export as marker_export
from tests.conftest import DummyViewer, Image, Labels


def test_find_layer_by_type() -> None:
    """Locate layers by class name.

    Returns
    -------
    None
    """
    viewer = DummyViewer([Labels(np.zeros((2, 2)), "labels"), Image(np.zeros((2, 2)), "img")])
    assert marker_export._find_layer(viewer, "labels", "Labels") is not None
    assert marker_export._find_layer(viewer, "img", "Image") is not None
    assert marker_export._find_layer(viewer, "missing", "Image") is None


def test_centroids_and_counts() -> None:
    """Compute centroids and pixel counts.

    Returns
    -------
    None
    """
    labels = np.array([[0, 1], [2, 2]], dtype=np.int32)
    ids, centroids = marker_export._compute_centroids(labels)
    counts = marker_export._pixel_counts(labels, ids)
    assert ids.tolist() == [1, 2]
    assert centroids.shape == (2, 2)
    assert counts.tolist() == [1, 2]


def test_intensity_sum_and_divide() -> None:
    """Summarize intensity and safe divide.

    Returns
    -------
    None
    """
    labels = np.array([[1, 1], [0, 2]], dtype=np.int32)
    image = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    sums = marker_export._intensity_sum(labels, image, np.array([1, 2]))
    assert sums.tolist() == [3.0, 4.0]
    divided = marker_export._safe_divide(np.array([1.0, 2.0]), np.array([1.0, 0.0]))
    assert divided.tolist() == [1.0, 0.0]


def test_pixel_sizes_helpers() -> None:
    """Resolve pixel sizes from metadata.

    Returns
    -------
    None
    """
    layer = Image(np.zeros((2, 2)), "img", metadata={"physical_pixel_sizes": {"X": 0.5, "Y": 1.5, "Z": 2.5}})
    sizes_2d = marker_export._pixel_sizes(layer, 2)
    sizes_3d = marker_export._pixel_sizes_from_metadata(0.5, 1.5, 2.5, 3)
    assert sizes_2d.tolist() == [1.5, 0.5]
    assert sizes_3d.tolist() == [2.5, 1.5, 0.5]


def test_initialize_rows_and_prefix() -> None:
    """Initialize rows with centroid info and channel prefix.

    Returns
    -------
    None
    """
    ids = np.array([1])
    centroids = np.array([[2.0, 3.0]])
    pixel_sizes = np.array([1.0, 2.0])
    rows = marker_export._initialize_rows(ids, centroids, pixel_sizes)
    assert rows[0]["centroid_y_pixels"] == 2.0
    assert rows[0]["centroid_x_um"] == 6.0
    channel = MarkerChannelConfig(name="Ch 1", channel="img")
    assert marker_export._channel_prefix(channel) == "ch_1"


def test_apply_threshold() -> None:
    """Apply threshold filtering to intensity vectors.

    Returns
    -------
    None
    """
    channel = MarkerChannelConfig(name="Ch1", channel="img", threshold_enabled=True, threshold_min=1.0)
    mean = np.array([0.5, 2.0], dtype=float)
    raw = np.array([1.0, 2.0], dtype=float)
    integ = np.array([3.0, 4.0], dtype=float)
    t_mean, t_raw, t_integ = marker_export._apply_threshold(mean, raw, integ, channel)
    assert t_mean.tolist() == [0.0, 2.0]
    assert t_raw.tolist() == [0.0, 2.0]
    assert t_integ.tolist() == [0.0, 4.0]
