"""RMP spot detector implementation."""

from __future__ import annotations

import logging

import numpy as np

from ..base import SenoQuantSpotDetector
from senoquant.tabs.spots.models.denoise import wavelet_denoise_input
from senoquant.utils import layer_data_asarray

from .anisotropy import (
    _estimate_apparent_z_anisotropy_ratio,
    _spot_call_with_anisotropy_correction,
)
from .config import (
    RMPSettings,
    RMP_TILE_CHUNK_SIZE,
    WAVELET_SIGMA,
)
from .markers import _markers_from_local_maxima, _segment_from_markers
from .normalization import (
    _clamp_threshold,
    _normalize_image,
    _normalize_top_hat_unit,
)
from .postprocess import _postprocess_top_hat
from .shape_utils import _fit_to_shape, _pad_xy_to_chunk_multiple, _zoom_to_shape
from .torch_ops import (
    F,
    torch,
    _ensure_torch_available,
    _grayscale_opening_tensor,
    _kernel_shape,
    _pad_tensor_for_rotation,
    _rmp_opening,
    _rotate_tensor,
    _to_image_tensor,
    _torch_device,
)
from .top_hat import (
    _cluster_client,
    _compute_top_hat,
    _compute_top_hat_2d,
    _compute_top_hat_nd,
    _dask_available,
    _distributed_available,
    _ensure_dask_available,
    _ensure_distributed_available,
    _recommended_overlap,
    _rmp_top_hat,
    _rmp_top_hat_block,
    _rmp_top_hat_block_mapped,
    _rmp_top_hat_tiled,
)


logger = logging.getLogger(__name__)


class RMPDetector(SenoQuantSpotDetector):
    """RMP spot detector implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("rmp", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run the RMP detector and return instance labels.

        Parameters
        ----------
        **kwargs
            layer : napari.layers.Image or None
                Image layer used for spot detection.
            settings : dict
                Detector settings keyed by the details.json schema.

        Returns
        -------
        dict
            Dictionary with ``mask`` key containing instance labels.
        """
        layer = kwargs.get("layer")
        if layer is None:
            return {"mask": None, "points": None}
        if getattr(layer, "rgb", False):
            raise ValueError("RMP requires single-channel images.")

        settings = kwargs.get("settings", {})
        manual_threshold = _clamp_threshold(
            float(settings.get("manual_threshold", 0.5))
        )
        config = RMPSettings(
            extraction_se_length=int(settings.get("extraction_kernel_length", 10)),
            angle_spacing=5,
            auto_threshold=bool(settings.get("auto_threshold", True)),
            manual_threshold=manual_threshold,
            enable_denoising=True,
        )

        if config.angle_spacing <= 0:
            raise ValueError("Angle spacing must be positive.")
        if config.extraction_se_length <= 0:
            raise ValueError("Structuring element lengths must be positive.")

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("RMP expects 2D images or 3D stacks.")

        normalized = _normalize_image(data)
        denoised = wavelet_denoise_input(
            normalized,
            enabled=config.enable_denoising,
            sigma=WAVELET_SIGMA,
        )

        use_distributed = False # This results in faster execution in most cases.
        use_tiled = _dask_available()
        top_hat_input = denoised
        top_hat_crop_slices: tuple[slice, ...] | None = None
        if use_tiled:
            top_hat_input, top_hat_crop_slices = _pad_xy_to_chunk_multiple(
                denoised,
                chunk_size=RMP_TILE_CHUNK_SIZE,
            )
        try:
            top_hat = _compute_top_hat_nd(
                top_hat_input,
                config,
                use_tiled=use_tiled,
                use_distributed=use_distributed,
            )
        except Exception:
            if not use_distributed:
                raise
            logger.warning(
                "RMP distributed tiled execution failed; retrying with single-threaded local execution.",
                exc_info=False,
            )
            top_hat = _compute_top_hat_nd(
                top_hat_input,
                config,
                use_tiled=use_tiled,
                use_distributed=False,
            )
        if top_hat_crop_slices is not None:
            top_hat = np.asarray(top_hat[top_hat_crop_slices], dtype=np.float32)
        denoised_top_hat = wavelet_denoise_input(
            top_hat,
            enabled=config.enable_denoising,
            sigma=WAVELET_SIGMA,
        )
        labels, _top_hat_normalized = _postprocess_top_hat(
            denoised_top_hat,
            config,
            reference_image=denoised,
        )
        return {
            "mask": labels,
            # "debug_images": {
            #     "debug_top_hat_before_threshold": _top_hat_normalized.astype(
            #         np.float32,
            #         copy=False,
            #     ),
            # },
        }
