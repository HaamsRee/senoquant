"""Tests for marker thresholding helpers.

Notes
-----
Checks error handling and valid outputs for threshold computations.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.quantification.features.marker.thresholding import compute_threshold


def test_compute_threshold_valid() -> None:
    """Compute a threshold using a valid method.

    Returns
    -------
    None
    """
    data = np.arange(10, dtype=np.float32)
    threshold = compute_threshold(data, "Otsu")
    assert isinstance(threshold, float)


def test_compute_threshold_invalid_method() -> None:
    """Raise on an invalid method name.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        compute_threshold([1, 2, 3], "Unknown")


def test_compute_threshold_empty() -> None:
    """Raise on empty data.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        compute_threshold([], "Otsu")
