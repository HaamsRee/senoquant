"""Tests for the RMP spot detector helpers.

Notes
-----
Exercises normalization, padding, and instance labeling helpers.
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


def test_pad_for_rotation_grows_canvas() -> None:
    """Pad image so rotations keep content.

    Returns
    -------
    None
    """
    data = np.zeros((4, 6), dtype=np.float32)
    padded, (pad_y, pad_x) = rmp._pad_for_rotation(data)
    assert padded.shape[0] >= data.shape[0]
    assert padded.shape[1] >= data.shape[1]
    assert pad_y >= 0 and pad_x >= 0


def test_binary_to_instances_offset() -> None:
    """Offset labels with a starting label.

    Returns
    -------
    None
    """
    mask = np.array([[1, 0], [0, 1]], dtype=bool)
    labeled, next_label = rmp._binary_to_instances(mask, start_label=5)
    assert labeled.max() >= 5
    assert next_label == labeled.max() + 1


def test_watershed_instances_empty() -> None:
    """Return zeros when binary mask is empty.

    Returns
    -------
    None
    """
    empty = np.zeros((3, 3), dtype=bool)
    labels = rmp._watershed_instances(np.zeros((3, 3)), empty, min_distance=1)
    assert labels.max() == 0
