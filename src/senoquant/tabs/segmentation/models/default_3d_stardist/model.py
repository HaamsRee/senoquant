"""Restored 3D StarDist ONNX model with voxel-spacing correction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy import ndimage as ndi

from senoquant.tabs.segmentation.stardist_onnx_utils import model_runtime


MODEL_GRID_ZYX = (2, 4, 4)
MODEL_RAY_ANISOTROPY_ZYX = (1.0, 1.03125, 1.0)
MODEL_TRAINING_SPACING_UM_ZYX = (0.2131, 0.2058, 0.2058)
MODEL_OBJECT_DIAMETER_REFERENCE_PX = 30.0
MODEL_N_RAYS = 128
MODEL_PROB_THRESHOLD = 0.4451190689256302
MODEL_NMS_THRESHOLD = 0.3


DEFAULT_3D_STARDIST_VARIANT = model_runtime.StarDistOnnxVariantConfig(
    model_key="default_3d_stardist",
    expected_ndim=3,
    expected_shape_label="3D (ZYX)",
    input_layout="NDHWC",
    prob_layout="NDHWC",
    dist_layout="NZYXR",
    object_diameter_reference_px=MODEL_OBJECT_DIAMETER_REFERENCE_PX,
    scale_axes=("Z", "Y", "X"),
    default_onnx_filename="default_3d.onnx",
    model_relative_candidates=(
        "onnx_models/default_3d.onnx",
        "default_3d.onnx",
    ),
    div_by_fallback=1,
    cap_xy_only=True,
    snap_skip_axes=(0,),
    enforce_post_snap_divisibility=False,
    require_stardist_3d=True,
    compiled_ops_error=(
        "3D StarDist labeling requires compiled ops; build extensions in "
        "stardist_onnx_utils/_stardist/lib."
    ),
)


def _physical_spacing_zyx(layer: object) -> tuple[float, float, float] | None:
    """Read a complete, positive ZYX voxel-size tuple from layer metadata."""
    metadata = getattr(layer, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    pixel_sizes = metadata.get("physical_pixel_sizes")
    if not isinstance(pixel_sizes, Mapping):
        return None
    try:
        spacing = tuple(float(pixel_sizes[axis]) for axis in ("Z", "Y", "X"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(np.isfinite(value) and value > 0 for value in spacing):
        return None
    return spacing


class StarDistOnnxModel(model_runtime.StarDistOnnxBaseModel):
    """Run the historical 3D StarDist model with its original geometry."""

    def __init__(self, models_root=None) -> None:
        super().__init__(
            variant=DEFAULT_3D_STARDIST_VARIANT,
            models_root=models_root,
        )
        self._last_scale_info: dict[str, Any] = {}

    def run(self, **kwargs) -> dict:
        """Run inference and record the resolved input scaling metadata."""
        settings = dict(kwargs.get("settings") or {})
        settings.setdefault("object_diameter_px", 30.0)
        settings.setdefault("prob_thresh", MODEL_PROB_THRESHOLD)
        settings.setdefault("nms_thresh", MODEL_NMS_THRESHOLD)
        result = super().run(**{**kwargs, "settings": settings})
        info = dict(result.get("info") or {})
        info["input_scale"] = dict(self._last_scale_info)
        result["info"] = info
        return result

    def _create_rays(self, n_rays: int):
        if n_rays != MODEL_N_RAYS:
            raise ValueError(
                f"Expected {MODEL_N_RAYS} StarDist rays, received {n_rays}."
            )
        return self._get_rays_class()(
            n=n_rays,
            anisotropy=MODEL_RAY_ANISOTROPY_ZYX,
        )

    def _infer_grid(self, *args, **kwargs) -> tuple[int, int, int]:
        """Return the grid saved with the original StarDist model."""
        return MODEL_GRID_ZYX

    def _scale_input(
        self,
        image: np.ndarray,
        settings: dict,
        *,
        layer=None,
    ) -> tuple[np.ndarray, dict[str, float] | None]:
        """Combine manual object-size scaling with voxel-spacing correction."""
        diameter_px = float(settings.get("object_diameter_px", 30.0))
        if diameter_px <= 0:
            raise ValueError("Object diameter (px) must be positive.")

        diameter_scale = MODEL_OBJECT_DIAMETER_REFERENCE_PX / diameter_px
        input_spacing = _physical_spacing_zyx(layer)
        if input_spacing is None:
            spacing_ratios = None
            anisotropy_scale = np.ones(3, dtype=np.float64)
            spacing_source = "unavailable"
            xy_reference = None
        else:
            spacing_ratios = np.asarray(input_spacing) / np.asarray(
                MODEL_TRAINING_SPACING_UM_ZYX
            )
            xy_reference = float(np.sqrt(spacing_ratios[1] * spacing_ratios[2]))
            anisotropy_scale = spacing_ratios / xy_reference
            spacing_source = "physical_pixel_sizes"

        scale_zyx = anisotropy_scale * diameter_scale
        self._last_scale_info = {
            "axes": "ZYX",
            "factors": tuple(float(value) for value in scale_zyx),
            "source": spacing_source,
            "input_spacing_um": input_spacing,
            "model_spacing_um": MODEL_TRAINING_SPACING_UM_ZYX,
            "spacing_ratios": (
                None
                if spacing_ratios is None
                else tuple(float(value) for value in spacing_ratios)
            ),
            "xy_reference_ratio": xy_reference,
            "anisotropy_factors": tuple(
                float(value) for value in anisotropy_scale
            ),
            "diameter_scale": float(diameter_scale),
        }

        if np.allclose(scale_zyx, 1.0):
            return image, None
        scaled = ndi.zoom(image, tuple(scale_zyx), order=1)
        if min(scaled.shape) < 1:
            raise ValueError(
                "Scaling factors produced an empty image; adjust object diameter."
            )
        scale = {
            axis: float(value)
            for axis, value in zip(("Z", "Y", "X"), scale_zyx)
        }
        return scaled.astype(np.float32, copy=False), scale


__all__ = [
    "MODEL_GRID_ZYX",
    "MODEL_N_RAYS",
    "MODEL_OBJECT_DIAMETER_REFERENCE_PX",
    "MODEL_RAY_ANISOTROPY_ZYX",
    "MODEL_TRAINING_SPACING_UM_ZYX",
    "StarDistOnnxModel",
]
