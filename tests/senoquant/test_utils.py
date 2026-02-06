"""Tests for shared utility helpers.

Notes
-----
These tests validate data coercion and shape handling for napari layer
conversions.
"""

from __future__ import annotations

import numpy as np

from senoquant.utils import append_run_metadata, layer_data_asarray


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


def test_append_run_metadata_appends_history() -> None:
    """Append a new run record while preserving previous run metadata."""
    metadata = {
        "path": "sample.tif",
        "run_history": [
            {
                "timestamp": "2026-02-06T00:00:00.000Z",
                "task": "nuclear",
                "runner_type": "segmentation_model",
                "runner_name": "default_2d",
                "settings": {"threshold": 0.5},
            }
        ],
    }

    updated = append_run_metadata(
        metadata,
        task="cytoplasmic",
        runner_type="segmentation_model",
        runner_name="nuclear_dilation",
        settings={"radius": 5},
    )

    assert updated["task"] == "cytoplasmic"
    assert updated["path"] == "sample.tif"
    history = updated["run_history"]
    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0]["runner_name"] == "default_2d"
    assert history[-1]["runner_name"] == "nuclear_dilation"
    assert history[-1]["settings"] == {"radius": 5}
    assert isinstance(history[-1]["timestamp"], str)
