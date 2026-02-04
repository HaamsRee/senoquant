"""Tests for the RMP spot detector helpers.

Notes
-----
Exercises normalization, padding, and marker/segmentation helpers.
"""

from __future__ import annotations

import numpy as np

from senoquant.tabs.spots.models.rmp import model as rmp


def test_normalize_image_constant() -> None:
    """Normalize constant image to zeros.

    Returns
    -------
    None
    """
    data = np.ones((4, 4), dtype=np.float32)
    normalized = rmp._normalize_image(data)
    assert np.allclose(normalized, 0.0)


def test_pad_tensor_for_rotation_grows_canvas() -> None:
    """Pad tensor so rotations keep content."""
    data = np.zeros((4, 6), dtype=np.float32)
    device = rmp._torch_device()
    tensor = rmp._to_image_tensor(data, device=device)
    padded, (pad_y, pad_x) = rmp._pad_tensor_for_rotation(tensor)
    assert int(padded.shape[-2]) >= data.shape[0]
    assert int(padded.shape[-1]) >= data.shape[1]
    assert pad_y >= 0 and pad_x >= 0


def test_markers_from_local_maxima_empty() -> None:
    """Return empty markers when no local maxima cross threshold."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.5)
    assert markers.shape == enhanced.shape
    assert markers.max() == 0


def test_segment_from_markers_empty_foreground() -> None:
    """Return zeros when threshold removes all foreground."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = np.zeros((4, 4), dtype=np.int32)
    labels = rmp._segment_from_markers(enhanced, markers, threshold=0.5)
    assert labels.shape == enhanced.shape
    assert labels.max() == 0
