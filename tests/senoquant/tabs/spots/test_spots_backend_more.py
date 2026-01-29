"""Additional tests for spots backend colocalization."""

from __future__ import annotations

import numpy as np

from senoquant.tabs.spots.backend import SpotsBackend


def test_compute_colocalization_empty() -> None:
    """Return empty points when no overlap exists.

    Returns
    -------
    None
    """
    data_a = np.zeros((2, 2), dtype=np.int32)
    data_b = np.ones((2, 2), dtype=np.int32)
    backend = SpotsBackend()
    result = backend.compute_colocalization(data_a, data_b)
    assert result["points"].shape[0] == 0
