"""Tests for centroid-based ROI geometry membership helpers."""

from __future__ import annotations

import numpy as np

# Importing the test conftest module installs lightweight dependency stubs.
import tests.conftest  # noqa: F401
from senoquant.tabs.quantification.features import roi_membership


class Shapes:
    """Minimal Shapes layer stub exposing geometry payload."""

    def __init__(self, data: list[np.ndarray], shape_type: str = "polygon") -> None:
        self.data = [np.asarray(item, dtype=float) for item in data]
        self.shape_type = [shape_type] * len(self.data)


def test_membership_from_layer_2d_polygon() -> None:
    """Evaluate 2D polygon membership directly from centroid coordinates."""
    polygon = np.array(
        [
            [-0.5, -0.5],
            [-0.5, 1.5],
            [1.5, 1.5],
            [1.5, -0.5],
        ],
        dtype=float,
    )
    layer = Shapes([polygon])
    centroids = np.array([[0.0, 0.0], [2.0, 2.0]], dtype=float)

    included = roi_membership.membership_from_layer(layer, centroids)

    assert included is not None
    assert included.tolist() == [True, False]


def test_membership_from_layer_3d_xy_polygon_propagates_z() -> None:
    """Apply XY ROI volume-wide by projecting over Z."""
    xy_polygon = np.array(
        [
            [1.0, 0.0, 0.0],
            [1.0, 0.0, 2.0],
            [1.0, 2.0, 2.0],
            [1.0, 2.0, 0.0],
        ],
        dtype=float,
    )
    layer = Shapes([xy_polygon])
    centroids = np.array(
        [
            [0.0, 1.0, 1.0],
            [2.0, 1.0, 1.0],
            [1.0, 2.5, 2.5],
        ],
        dtype=float,
    )

    included = roi_membership.membership_from_layer(layer, centroids)

    assert included is not None
    assert included.tolist() == [True, True, False]


def test_membership_from_layer_3d_xz_polygon_propagates_y() -> None:
    """Apply XZ ROI volume-wide by projecting over Y."""
    xz_polygon = np.array(
        [
            [0.0, 1.0, 0.0],
            [0.0, 1.0, 2.0],
            [2.0, 1.0, 2.0],
            [2.0, 1.0, 0.0],
        ],
        dtype=float,
    )
    layer = Shapes([xz_polygon])
    centroids = np.array(
        [
            [1.0, 0.0, 1.0],
            [1.0, 2.0, 1.0],
            [2.5, 1.0, 2.5],
        ],
        dtype=float,
    )

    included = roi_membership.membership_from_layer(layer, centroids)

    assert included is not None
    assert included.tolist() == [True, True, False]


def test_membership_from_layer_3d_yz_polygon_propagates_x() -> None:
    """Apply YZ ROI volume-wide by projecting over X."""
    yz_polygon = np.array(
        [
            [0.0, 0.0, 1.0],
            [0.0, 2.0, 1.0],
            [2.0, 2.0, 1.0],
            [2.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    layer = Shapes([yz_polygon])
    centroids = np.array(
        [
            [1.0, 1.0, 0.0],
            [1.0, 1.0, 2.0],
            [2.5, 2.5, 1.0],
        ],
        dtype=float,
    )

    included = roi_membership.membership_from_layer(layer, centroids)

    assert included is not None
    assert included.tolist() == [True, True, False]
