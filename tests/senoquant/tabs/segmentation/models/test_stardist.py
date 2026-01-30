"""Tests for StarDist ONNX model helpers.

Notes
-----
Focuses on input scaling and validation utilities without running ONNX
inference.
"""

from __future__ import annotations

import importlib

import numpy as np
import pytest


@pytest.mark.parametrize(
    "module_path",
    [
        "senoquant.tabs.segmentation.models.default_2d.model",
    ],
)
def test_stardist_2d_helpers(module_path: str) -> None:
    """Validate 2D helper methods.

    Returns
    -------
    None
    """
    module = importlib.import_module(module_path)
    model = module.StarDistOnnxModel(models_root=None)
    image = np.array([[0.0, 1.0]], dtype=np.float32)
    scaled = model._scale_intensity(image)
    assert np.isclose(scaled.min(), 0.0)
    assert np.isclose(scaled.max(), 1.0)
    with pytest.raises(ValueError):
        model._scale_input(image, {"object_diameter_px": 0})
    with pytest.raises(ValueError):
        model._extract_layer_data(None, required=True)


def test_stardist_3d_scale_input() -> None:
    """Scale 3D input with valid diameter.

    Returns
    -------
    None
    """
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_3d.model"
    )
    model = module.StarDistOnnxModel(models_root=None)
    image = np.zeros((3, 3, 3), dtype=np.float32)
    scaled, scale = model._scale_input(image, {"object_diameter_px": 30})
    assert scaled.shape == image.shape
    assert scale is None
