"""Default 3D StarDist ONNX model definition.

This module defines the concrete 3D model variant by providing a
``StarDistOnnxVariantConfig`` and wiring it into the shared runtime base.
"""

from __future__ import annotations

from senoquant.tabs.segmentation.stardist_onnx_utils import model_runtime


# Variant constants used by the shared StarDist ONNX runtime.
DEFAULT_3D_VARIANT = model_runtime.StarDistOnnxVariantConfig(
    model_key="default_3d",
    expected_ndim=3,
    expected_shape_label="3D (ZYX)",
    input_layout="NDHWC",
    prob_layout="NDHWC",
    dist_layout="NZYXR",
    object_diameter_reference_px=30.0,
    scale_axes=("Z", "Y", "X"),
    default_onnx_filename="default_3d.onnx",
    model_relative_candidates=(
        "onnx_models/default_3d.onnx",
        "default_3d.onnx",
        "onnx_models/stardist3d_3D_demo.onnx",
        "stardist3d_3D_demo.onnx",
        "stardist3d.onnx",
    ),
    div_by_fallback=1,
    cap_xy_only=True,
    snap_skip_axes=(0,),
    enforce_post_snap_divisibility=False,
    require_stardist_3d=True,
    compiled_ops_error=(
        "3D StarDist labeling requires compiled ops; build "
        "extensions in stardist_onnx_utils/_stardist/lib."
    ),
)


class StarDistOnnxModel(model_runtime.StarDistOnnxBaseModel):
    """Concrete StarDist ONNX 3D model wrapper.

    Notes
    -----
    All runtime behavior is implemented in
    :class:`senoquant.tabs.segmentation.stardist_onnx_utils.model_runtime.StarDistOnnxBaseModel`.
    This class only binds the 3D variant configuration.
    """

    def __init__(self, models_root=None) -> None:
        """Initialize the default 3D StarDist ONNX model.

        Parameters
        ----------
        models_root : pathlib.Path or None, optional
            Optional root directory containing segmentation model folders.
        """
        super().__init__(variant=DEFAULT_3D_VARIANT, models_root=models_root)
