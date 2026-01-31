"""Tests for spot size filtering functionality."""

import numpy as np

from senoquant.tabs.spots.frontend import _filter_labels_by_size


def test_filter_no_filtering_when_both_zero() -> None:
    """Test that no filtering occurs when both min and max are 0."""
    mask = np.array([[1, 1, 0], [0, 2, 2], [0, 0, 2]])
    result = _filter_labels_by_size(mask, min_size=0, max_size=0)
    np.testing.assert_array_equal(result, mask)


def test_filter_removes_small_spots() -> None:
    """Test that spots below min_size are removed."""
    # Create a mask with two spots: one with 2 pixels, one with 4 pixels
    mask = np.array([
        [1, 1, 0, 0],
        [0, 0, 2, 2],
        [0, 0, 2, 2],
        [0, 0, 0, 0],
    ])
    # Filter to keep only spots >= 3 pixels
    result = _filter_labels_by_size(mask, min_size=3, max_size=0)
    expected = np.array([
        [0, 0, 0, 0],
        [0, 0, 2, 2],
        [0, 0, 2, 2],
        [0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_removes_large_spots() -> None:
    """Test that spots above max_size are removed."""
    # Create a mask with two spots: one with 2 pixels, one with 4 pixels
    mask = np.array([
        [1, 1, 0, 0],
        [0, 0, 2, 2],
        [0, 0, 2, 2],
        [0, 0, 0, 0],
    ])
    # Filter to keep only spots <= 3 pixels
    result = _filter_labels_by_size(mask, min_size=0, max_size=3)
    expected = np.array([
        [1, 1, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_with_min_and_max() -> None:
    """Test filtering with both min and max size."""
    # Create a mask with three spots: 2, 4, and 6 pixels
    mask = np.array([
        [1, 1, 0, 0, 0, 0],
        [0, 0, 2, 2, 0, 0],
        [0, 0, 2, 2, 0, 0],
        [0, 0, 0, 0, 3, 3],
        [0, 0, 0, 0, 3, 3],
        [0, 0, 0, 0, 3, 3],
    ])
    # Filter to keep only spots between 3 and 5 pixels
    result = _filter_labels_by_size(mask, min_size=3, max_size=5)
    expected = np.array([
        [0, 0, 0, 0, 0, 0],
        [0, 0, 2, 2, 0, 0],
        [0, 0, 2, 2, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0],
    ])
    np.testing.assert_array_equal(result, expected)


def test_filter_empty_mask() -> None:
    """Test filtering with an empty mask."""
    mask = np.zeros((5, 5), dtype=int)
    result = _filter_labels_by_size(mask, min_size=2, max_size=10)
    np.testing.assert_array_equal(result, mask)
