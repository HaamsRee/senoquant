"""Tests for spot size filtering functionality."""

import numpy as np

from senoquant.tabs.spots.frontend import _filter_labels_by_size


def test_filter_no_filtering_when_both_zero() -> None:
    """Test that no filtering occurs when both min and max are 0."""
    mask = np.array([[1, 1, 0], [0, 2, 2], [0, 0, 2]])
    result = _filter_labels_by_size(mask, min_size=0, max_size=0)
    np.testing.assert_array_equal(result, mask)


def test_filter_removes_small_spots() -> None:
    """Test that spots below min effective area are removed in 2D."""
    mask = np.array([
        [1, 1, 0, 2, 2, 2],
        [1, 1, 0, 2, 2, 2],
        [0, 0, 0, 2, 2, 2],
        [0, 0, 0, 0, 0, 0],
    ])
    # min_size=3 means min area ~= 7.07 px^2, so only area=9 survives.
    result = _filter_labels_by_size(mask, min_size=3, max_size=0)
    expected = np.array([
        [0, 0, 0, 2, 2, 2],
        [0, 0, 0, 2, 2, 2],
        [0, 0, 0, 2, 2, 2],
        [0, 0, 0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_removes_large_spots() -> None:
    """Test that spots above max effective area are removed in 2D."""
    mask = np.array([
        [1, 1, 0, 2, 2, 2],
        [1, 1, 0, 2, 2, 2],
        [0, 0, 0, 2, 2, 2],
        [0, 0, 0, 0, 0, 0],
    ])
    # max_size=3 means max area ~= 7.07 px^2, so area=4 survives and area=9 is removed.
    result = _filter_labels_by_size(mask, min_size=0, max_size=3)
    expected = np.array([
        [1, 1, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_with_min_and_max() -> None:
    """Test 2D filtering with both min and max diameters."""
    mask = np.array([
        [1, 0, 0, 2, 2, 0, 3, 3, 3],
        [0, 0, 0, 2, 2, 0, 3, 3, 3],
        [0, 0, 0, 0, 0, 0, 3, 3, 3],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
    ])
    # Keep equivalent area between diameters 2 and 3:
    # min area ~= 3.14, max area ~= 7.07. Only area=4 survives.
    result = _filter_labels_by_size(mask, min_size=2, max_size=3)
    expected = np.array([
        [0, 0, 0, 2, 2, 0, 0, 0, 0],
        [0, 0, 0, 2, 2, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_empty_mask() -> None:
    """Test filtering with an empty mask."""
    mask = np.zeros((5, 5), dtype=int)
    result = _filter_labels_by_size(mask, min_size=2, max_size=10)
    np.testing.assert_array_equal(result, mask)


def test_filter_3d_uses_effective_volume() -> None:
    """Test that 3D filtering uses spherical effective volume thresholds."""
    mask = np.zeros((5, 5, 5), dtype=int)
    mask[0:2, 0:2, 0:2] = 1  # volume = 8
    mask[2:5, 2:5, 2:5] = 2  # volume = 27

    # max_size=3 means max volume ~= 14.14 px^3, so label 1 stays and label 2 is removed.
    result = _filter_labels_by_size(mask, min_size=0, max_size=3)

    expected = np.zeros_like(mask)
    expected[0:2, 0:2, 0:2] = 1
    np.testing.assert_array_equal(result, expected)
