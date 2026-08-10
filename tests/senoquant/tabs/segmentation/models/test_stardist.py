"""Tests for StarDist ONNX model helpers.

Notes
-----
Focuses on input scaling and validation utilities without running ONNX
inference.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_stardist_2d_infer_tiling_uses_graph_divisibility(monkeypatch) -> None:
    """Use inferred ONNX divisibility constraints for tile sizing."""
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_2d.model"
    )
    model = module.StarDistOnnxModel(models_root=None)
    image = np.zeros((300, 300), dtype=np.float32)

    monkeypatch.setattr(
        "senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.infer_div_by",
        lambda _path, ndim=None: (32,) * int(ndim or 2),
    )
    monkeypatch.setattr(
        "senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.receptive_field.recommend_tile_overlap",
        lambda _path, ndim=None: (0,) * int(ndim or 2),
    )
    monkeypatch.setattr(
        "senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.valid_sizes.infer_valid_size_patterns_from_path",
        lambda *_args, **_kwargs: None,
    )

    tile_shape, _overlap = model._infer_tiling(
        image,
        Path("dummy.onnx"),
        None,
        "",
        [],
        "NHWC",
    )

    assert all(ts % 32 == 0 for ts in tile_shape)


def test_stardist_3d_restores_model_geometry(tmp_path: Path, monkeypatch) -> None:
    """Use the original fixed grid and anisotropic 128-ray definition."""
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_3d_stardist.model"
    )
    model = module.StarDistOnnxModel(models_root=tmp_path)
    captured = {}

    class DummyRays:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(model, "_get_rays_class", lambda: DummyRays)

    assert model._infer_grid() == (2, 4, 4)
    model._create_rays(128)
    assert captured == {"n": 128, "anisotropy": (1.0, 1.03125, 1.0)}
    with pytest.raises(ValueError, match="Expected 128"):
        model._create_rays(96)


def test_stardist_3d_corrects_independent_voxel_geometry(tmp_path: Path) -> None:
    """Correct relative ZYX geometry without assuming isotropic XY pixels."""
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_3d_stardist.model"
    )
    model = module.StarDistOnnxModel(models_root=tmp_path)
    training_spacing = module.MODEL_TRAINING_SPACING_UM_ZYX
    spacing_ratios = (2.0, 2.0, 0.5)
    layer = SimpleNamespace(
        metadata={
            "physical_pixel_sizes": {
                axis: ratio * value
                for axis, ratio, value in zip(
                    ("Z", "Y", "X"),
                    spacing_ratios,
                    training_spacing,
                )
            }
        }
    )
    image = np.zeros((2, 3, 8), dtype=np.float32)

    scaled, scale = model._scale_input(
        image,
        {"object_diameter_px": 60.0},
        layer=layer,
    )

    assert scaled.shape == (2, 3, 2)
    assert scale == pytest.approx({"Z": 1.0, "Y": 1.0, "X": 0.25})
    assert model._last_scale_info["source"] == "physical_pixel_sizes"
    assert model._last_scale_info["model_spacing_um"] == training_spacing
    assert model._last_scale_info["spacing_ratios"] == pytest.approx(
        spacing_ratios
    )
    assert model._last_scale_info["anisotropy_factors"] == pytest.approx(
        (2.0, 2.0, 0.5)
    )


def test_stardist_3d_metadata_does_not_duplicate_uniform_size_scale(
    tmp_path: Path,
) -> None:
    """Reserve uniform scaling for the object-diameter setting."""
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_3d_stardist.model"
    )
    model = module.StarDistOnnxModel(models_root=tmp_path)
    training_spacing = module.MODEL_TRAINING_SPACING_UM_ZYX
    layer = SimpleNamespace(
        metadata={
            "physical_pixel_sizes": {
                axis: 2 * value
                for axis, value in zip(("Z", "Y", "X"), training_spacing)
            }
        }
    )
    image = np.zeros((2, 3, 4), dtype=np.float32)

    scaled, scale = model._scale_input(
        image,
        {"object_diameter_px": 30.0},
        layer=layer,
    )

    assert scaled is image
    assert scale is None
    assert model._last_scale_info["anisotropy_factors"] == pytest.approx(
        (1.0, 1.0, 1.0)
    )


def test_stardist_3d_spacing_fallback_and_manual_scale(tmp_path: Path) -> None:
    """Fall back safely when metadata is absent while retaining size scaling."""
    module = importlib.import_module(
        "senoquant.tabs.segmentation.models.default_3d_stardist.model"
    )
    model = module.StarDistOnnxModel(models_root=tmp_path)
    image = np.zeros((4, 4, 4), dtype=np.float32)

    scaled, scale = model._scale_input(
        image,
        {"object_diameter_px": 60.0},
        layer=SimpleNamespace(metadata={}),
    )

    assert scaled.shape == (2, 2, 2)
    assert scale == {"Z": 0.5, "Y": 0.5, "X": 0.5}
    assert model._last_scale_info["source"] == "unavailable"
    assert model._last_scale_info["input_spacing_um"] is None


def test_stardist_3d_postprocessing_returns_to_input_coordinates(
    monkeypatch,
) -> None:
    """Invert independent ZYX factors and rasterize at the input shape."""
    post = importlib.import_module(
        "senoquant.tabs.segmentation.stardist_onnx_utils."
        "onnx_framework.post.core"
    )
    points = np.array([[8.0, 9.0, 10.0]], dtype=np.float32)
    scores = np.array([0.9], dtype=np.float32)
    distances = np.ones((1, 128), dtype=np.float32)
    captured = {}

    def fake_nms(*_args, **_kwargs):
        return points.copy(), scores, distances

    def fake_rasterize(_dist, raster_points, *, rays, shape, **_kwargs):
        captured["points"] = raster_points.copy()
        captured["shape"] = shape
        return np.zeros(shape, dtype=np.uint16)

    class DummyRays:
        def copy(self, scale):
            captured["ray_scale"] = scale
            return self

    monkeypatch.setitem(
        sys.modules,
        "senoquant.tabs.segmentation.stardist_onnx_utils._stardist.nms",
        SimpleNamespace(non_maximum_suppression_3d=fake_nms),
    )
    monkeypatch.setitem(
        sys.modules,
        "senoquant.tabs.segmentation.stardist_onnx_utils."
        "_stardist.geometry.geom3d",
        SimpleNamespace(polyhedron_to_label=fake_rasterize),
    )

    labels, info = post.instances_from_prediction_3d(
        np.zeros((2, 2, 2), dtype=np.float32),
        np.zeros((2, 2, 2, 128), dtype=np.float32),
        grid=(2, 4, 4),
        prob_thresh=0.4,
        nms_thresh=0.3,
        rays=DummyRays(),
        scale={"Z": 2.0, "Y": 3.0, "X": 4.0},
        img_shape=(5, 6, 7),
    )

    assert labels.shape == (5, 6, 7)
    np.testing.assert_allclose(info["points"], [[4.0, 3.0, 2.5]])
    np.testing.assert_allclose(captured["points"], [[4.0, 3.0, 2.5]])
    assert captured["ray_scale"] == pytest.approx((0.5, 1 / 3, 0.25))
    assert captured["shape"] == (5, 6, 7)
