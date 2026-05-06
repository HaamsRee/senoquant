"""RMP spot detector implementation."""

from __future__ import annotations

from contextlib import contextmanager
from functools import partial
import logging
from typing import Iterable

import numpy as np
from skimage.filters import threshold_otsu

from ..base import SenoQuantSpotDetector
from senoquant.tabs.spots.models.denoise import wavelet_denoise_input
from senoquant.utils import layer_data_asarray

from .anisotropy import (
    _estimate_apparent_z_anisotropy_ratio,
    _spot_call_with_anisotropy_correction,
)
from .config import (
    MIN_SCALE_SIGMA,
    NOISE_FLOOR_SIGMA,
    RMPSettings,
    RMP_TILE_CHUNK_SIZE,
    SIGNAL_SCALE_QUANTILE,
    WAVELET_SIGMA,
    Array2D,
    KernelShape,
)
from .markers import _markers_from_local_maxima, _segment_from_markers
from .normalization import (
    _clamp_threshold,
    _normalize_image,
    _normalize_top_hat_unit,
)
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

try:
    import dask.array as da
except ImportError:  # pragma: no cover - optional dependency
    da = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from dask.distributed import Client, LocalCluster
except ImportError:  # pragma: no cover - optional dependency
    Client = None  # type: ignore[assignment]
    LocalCluster = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


def _rmp_top_hat(
    input_image: Array2D,
    structuring_element: Array2D,
    rotation_angles: Iterable[int],
) -> Array2D:
    """Return the top-hat (background subtracted) image."""
    opened_image = _rmp_opening(input_image, structuring_element, rotation_angles)
    return input_image - opened_image


def _compute_top_hat(input_image: Array2D, config: "RMPSettings") -> Array2D:
    """Compute the RMP top-hat response for a 2D image."""
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    return _rmp_top_hat(input_image, extraction_se, rotation_angles)


def _ensure_dask_available() -> None:
    """Ensure dask is installed for tiled execution."""
    if da is None:  # pragma: no cover - import guard
        raise ImportError("dask is required for distributed spot detection.")


def _ensure_distributed_available() -> None:
    """Ensure dask.distributed is installed for distributed execution."""
    if Client is None or LocalCluster is None:  # pragma: no cover - import guard
        raise ImportError("dask.distributed is required for distributed execution.")


def _dask_available() -> bool:
    """Return True when dask is available."""
    return da is not None


def _distributed_available() -> bool:
    """Return True when dask.distributed is available."""
    return Client is not None and LocalCluster is not None and da is not None


def _recommended_overlap(config: "RMPSettings") -> int:
    """Derive a suitable overlap from extraction structuring-element size."""
    return max(1, config.extraction_se_length * 2)


@contextmanager
def _cluster_client():
    """Yield a connected Dask client backed by a local cluster."""
    _ensure_distributed_available()
    with LocalCluster() as cluster:
        with Client(cluster) as client:
            yield client


def _rmp_top_hat_block(block: np.ndarray, config: "RMPSettings") -> np.ndarray:
    """Return background-subtracted tile via the RMP top-hat pipeline."""
    extraction_se: KernelShape = (1, config.extraction_se_length)
    rotation_angles = tuple(range(0, 180, config.angle_spacing))
    top_hat = block - _rmp_opening(block, extraction_se, rotation_angles)
    return np.asarray(top_hat, dtype=np.float32)


def _rmp_top_hat_block_mapped(
    block: np.ndarray,
    *,
    config: "RMPSettings",
    block_info=None,
) -> np.ndarray:
    """Top-level map_overlap callable for picklable tiled execution."""
    del block_info
    return _rmp_top_hat_block(block, config)


def _compute_top_hat_2d(
    image_2d: np.ndarray,
    config: "RMPSettings",
    *,
    use_tiled: bool,
    distributed: bool,
    client: "Client | None" = None,
) -> np.ndarray:
    """Compute a top-hat image for one 2D plane."""
    if use_tiled:
        return _rmp_top_hat_tiled(
            image_2d,
            config=config,
            distributed=distributed,
            client=client,
        )
    return _compute_top_hat(image_2d, config)


def _compute_top_hat_nd(
    image: np.ndarray,
    config: "RMPSettings",
    *,
    use_tiled: bool,
    use_distributed: bool,
) -> np.ndarray:
    """Compute top-hat for 2D images or slice-wise for 3D stacks."""
    if image.ndim == 2:
        return _compute_top_hat_2d(
            image,
            config,
            use_tiled=use_tiled,
            distributed=use_distributed,
        )

    top_hat_stack = np.zeros_like(image, dtype=np.float32)
    if use_tiled and use_distributed:
        with _cluster_client() as client:
            for z in range(image.shape[0]):
                top_hat_stack[z] = _compute_top_hat_2d(
                    image[z],
                    config,
                    use_tiled=True,
                    distributed=True,
                    client=client,
                )
        return top_hat_stack

    for z in range(image.shape[0]):
        top_hat_stack[z] = _compute_top_hat_2d(
            image[z],
            config,
            use_tiled=use_tiled,
            distributed=False,
        )
    return top_hat_stack


def _postprocess_top_hat(
    top_hat: np.ndarray,
    config: "RMPSettings",
    *,
    reference_image: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply normalization, thresholding, marker extraction, and watershed."""
    top_hat_normalized = _normalize_top_hat_unit(top_hat)
    reference = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else top_hat_normalized
    )
    if reference.shape != top_hat_normalized.shape:
        raise ValueError("Reference image shape must match top-hat shape.")
    threshold = (
        _clamp_threshold(float(threshold_otsu(top_hat_normalized)))
        if config.auto_threshold
        else config.manual_threshold
    )
    labels = _spot_call_with_anisotropy_correction(
        top_hat_normalized,
        threshold,
        reference_image=reference,
    )
    return labels, top_hat_normalized


def _rmp_top_hat_tiled(
    image: np.ndarray,
    config: "RMPSettings",
    chunk_size: tuple[int, int] = RMP_TILE_CHUNK_SIZE,
    overlap: int | None = None,
    distributed: bool = False,
    client: "Client | None" = None,
) -> np.ndarray:
    """Return the RMP top-hat image using tiled execution."""
    _ensure_dask_available()

    effective_overlap = _recommended_overlap(config) if overlap is None else overlap
    block_fn = partial(_rmp_top_hat_block_mapped, config=config)

    arr = da.from_array(image.astype(np.float32, copy=False), chunks=chunk_size)
    result = arr.map_overlap(
        block_fn,
        depth=(effective_overlap, effective_overlap),
        boundary="reflect",
        dtype=np.float32,
        trim=True,
    )

    if distributed:
        _ensure_distributed_available()
        if client is None:
            with _cluster_client() as temp_client:
                return temp_client.compute(result).result()
        return client.compute(result).result()

    return result.compute(scheduler="single-threaded")


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

        use_distributed = _distributed_available()
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
