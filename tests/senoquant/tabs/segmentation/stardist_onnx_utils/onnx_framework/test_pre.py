"""Tests for ONNX preprocessing helpers.

Notes
-----
Exercises normalization, padding, and unpadding utilities.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import pre


def test_validate_image_rejects_invalid_dim() -> None:
    """Reject non-2D/3D images.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        pre.validate_image(np.zeros((1, 2, 3, 4)))


def test_normalize_scales_values() -> None:
    """Normalize image to [0, 1].

    Returns
    -------
    None
    """
    image = np.arange(10, dtype=np.float32)
    normed = pre.normalize(image, pmin=0, pmax=100)
    assert normed.min() >= 0.0
    assert normed.max() <= 1.0


def test_pad_to_multiple() -> None:
    """Pad image to divisibility constraints.

    Returns
    -------
    None
    """
    image = np.zeros((5, 6), dtype=np.float32)
    padded, pads = pre.pad_to_multiple(image, (4, 4))
    assert padded.shape[0] % 4 == 0
    assert padded.shape[1] % 4 == 0
    assert pads[0][0] == 0 and pads[1][0] == 0


def test_unpad_to_shape() -> None:
    """Remove padding according to pads.

    Returns
    -------
    None
    """
    image = np.zeros((8, 8), dtype=np.float32)
    pads = ((0, 2), (0, 2))
    cropped = pre.unpad_to_shape(image, pads, scale=(1, 1))
    assert cropped.shape == (6, 6)


def test_pad_for_tiling() -> None:
    """Pad image for tiled prediction.

    Returns
    -------
    None
    """
    image = np.zeros((5, 5), dtype=np.float32)
    padded, pads = pre.pad_for_tiling(
        image, grid=(1, 1), tile_shape=(4, 4), overlap=(1, 1)
    )
    assert padded.shape[0] >= image.shape[0]
    assert pads[0][0] == 0
