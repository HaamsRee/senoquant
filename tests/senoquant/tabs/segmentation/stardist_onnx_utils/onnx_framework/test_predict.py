"""Tests for ONNX prediction helpers.

Notes
-----
Uses a dummy ONNX session to validate tiling and layout handling.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework import predict


class DummySession:
    """Minimal ONNX session stub."""

    def run(self, _output_names, feeds):
        input_tensor = next(iter(feeds.values()))
        # Expect NHWC input for 2D case.
        if input_tensor.ndim != 4:
            raise ValueError("Unexpected input ndim")
        _, height, width, _channels = input_tensor.shape
        prob = np.ones((1, height, width, 1), dtype=np.float32)
        dist = np.ones((1, height, width, 2), dtype=np.float32)
        return [prob, dist]


def test_default_tiling_spec_validation() -> None:
    """Reject tile shapes that do not match dimensions.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        predict.default_tiling_spec((4, 4), tile_shape=(4, 4, 4))


def test_predict_tiled_simple() -> None:
    """Run tiled prediction with a dummy session.

    Returns
    -------
    None
    """
    image = np.zeros((4, 4), dtype=np.float32)
    session = DummySession()
    prob, dist = predict.predict_tiled(
        image,
        session,
        input_name="input",
        output_names=["prob", "dist"],
        grid=(1, 1),
        input_layout="NHWC",
        prob_layout="NHWC",
        dist_layout="NYXR",
        tile_shape=(4, 4),
        overlap=(0, 0),
    )
    assert prob.shape == (4, 4)
    assert dist.shape == (4, 4, 2)
