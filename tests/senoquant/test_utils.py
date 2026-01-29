"""Tests for shared utility helpers.

Notes
-----
These tests validate data coercion and shape handling for napari layer
conversions.
"""

from __future__ import annotations

import numpy as np

from senoquant.utils import layer_data_asarray


class DummyLayer:
    """Simple layer stub for data access."""

    def __init__(self, data) -> None:
        self.data = data


def test_layer_data_asarray_squeezes() -> None:
    """Validate that layer data is converted and squeezed.

    Returns
    -------
    None
    """
    layer = DummyLayer(np.ones((1, 2, 2, 1)))
    result = layer_data_asarray(layer)
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 2)


def test_layer_data_asarray_preserves_shape() -> None:
    """Validate that squeeze can be disabled.

    Returns
    -------
    None
    """
    layer = DummyLayer([[1, 2], [3, 4]])
    result = layer_data_asarray(layer, squeeze=False)
    assert result.shape == (2, 2)
