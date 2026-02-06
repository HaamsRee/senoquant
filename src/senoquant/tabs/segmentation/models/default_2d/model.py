"""Default 2D StarDist ONNX model definition.

This module defines the concrete 2D model variant by providing a
``StarDistOnnxVariantConfig`` and wiring it into the shared runtime base.
"""

from __future__ import annotations

from senoquant.tabs.segmentation.stardist_onnx_utils import model_runtime


# Variant constants used by the shared StarDist ONNX runtime.
DEFAULT_2D_VARIANT = model_runtime.StarDistOnnxVariantConfig(
    model_key="default_2d",
    expected_ndim=2,
    expected_shape_label="2D (YX)",
    input_layout="NHWC",
    prob_layout="NHWC",
    dist_layout="NYXR",
    object_diameter_reference_px=17.44,
    scale_axes=("Y", "X"),
    default_onnx_filename="default_2d.onnx",
    model_relative_candidates=(
        "onnx_models/default_2d.onnx",
        "default_2d.onnx",
        "onnx_models/stardist_mod_2d.onnx",
        "onnx_models/stardist2d_2D_versatile_fluo.onnx",
        "stardist_mod_2d.onnx",
        "stardist2d_2D_versatile_fluo.onnx",
        "stardist2d.onnx",
    ),
    div_by_fallback=16,
    cap_xy_only=False,
    snap_skip_axes=(),
    enforce_post_snap_divisibility=True,
    require_stardist_3d=False,
    compiled_ops_error=(
        "StarDist 2D compiled ops are missing. Build the "
        "extensions in stardist_onnx_utils/_stardist/lib."
    ),
)


class StarDistOnnxModel(model_runtime.StarDistOnnxBaseModel):
    """Concrete StarDist ONNX 2D model wrapper.

    Notes
    -----
    All runtime behavior is implemented in
    :class:`senoquant.tabs.segmentation.stardist_onnx_utils.model_runtime.StarDistOnnxBaseModel`.
    This class only binds the 2D variant configuration.
    """

    def __init__(self, models_root=None) -> None:
        """Initialize the default 2D StarDist ONNX model.

        Parameters
        ----------
        models_root : pathlib.Path or None, optional
            Optional root directory containing segmentation model folders.
        """
        super().__init__(variant=DEFAULT_2D_VARIANT, models_root=models_root)
