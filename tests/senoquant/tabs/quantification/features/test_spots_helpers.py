"""Tests for spots export helper utilities."""

from __future__ import annotations

import numpy as np

from senoquant.tabs.quantification.features.spots import export as spots_export


def test_spot_cell_ids_from_centroids() -> None:
    """Assign cell ids from centroid coordinates.

    Returns
    -------
    None
    """
    cells = np.array([[1, 0], [2, 2]], dtype=np.int32)
    centroids = np.array([[0.0, 0.0], [1.0, 1.0]])
    ids = spots_export._spot_cell_ids_from_centroids(cells, centroids)
    assert ids.tolist() == [1, 2]


def test_cell_spot_metrics() -> None:
    """Compute per-cell spot counts and means.

    Returns
    -------
    None
    """
    cell_ids = np.array([1, 2, 2])
    means = np.array([1.0, 3.0, 5.0])
    counts, avg = spots_export._cell_spot_metrics(cell_ids, means, max_cell=2)
    assert counts.tolist() == [0, 1, 2]
    assert np.allclose(avg[1:], [1.0, 4.0])


def test_sanitize_and_channel_label() -> None:
    """Sanitize labels and build channel label.

    Returns
    -------
    None
    """
    assert spots_export._sanitize_name("Ch 1") == "ch_1"
    channel = type("Channel", (), {"name": "Spot A", "channel": "img"})()
    assert spots_export._channel_label(channel) == "Spot A"
    assert spots_export._sanitize_name(spots_export._channel_label(channel)) == "spot_a"


def test_safe_divide_handles_zero() -> None:
    """Return zeros where denominator is zero.

    Returns
    -------
    None
    """
    result = spots_export._safe_divide(np.array([1.0, 2.0]), np.array([1.0, 0.0]))
    assert result.tolist() == [1.0, 0.0]
