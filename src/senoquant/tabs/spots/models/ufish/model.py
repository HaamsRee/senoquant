"""U-FISH local-maxima seeded watershed detector."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import laplace
from skimage.morphology import local_maxima
from skimage.segmentation import watershed

from ..base import SenoQuantSpotDetector
from senoquant.tabs.spots.models.denoise import wavelet_denoise_input
from senoquant.utils import layer_data_asarray
from senoquant.tabs.spots.ufish_utils import UFishConfig, enhance_image


DEFAULT_THRESHOLD = 0.5
USE_LAPLACE_FOR_PEAKS = False
DEFAULT_DENOISE_ENABLED = True
DEFAULT_SPOT_SIZE = 1.0
MIN_SPOT_SIZE = 0.25
MAX_SPOT_SIZE = 4.0
EPS = 1e-6
NOISE_FLOOR_SIGMA = 1.5
MIN_SCALE_SIGMA = 5.0
SIGNAL_SCALE_QUANTILE = 99.9
INPUT_LOW_PERCENTILE = 0.05
INPUT_HIGH_PERCENTILE = 99.95


def _clamp_threshold(value: float) -> float:
    """Clamp threshold to the inclusive [0.0, 1.0] range."""
    return float(np.clip(value, 0.0, 1.0))


def _normalize_input_percentile(image: np.ndarray) -> np.ndarray:
    """Normalize input image to [0, 1] via percentile clipping."""
    data = np.asarray(image, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not np.any(finite_mask):
        return np.zeros_like(data, dtype=np.float32)

    valid = data[finite_mask]
    low, high = np.nanpercentile(valid, [INPUT_LOW_PERCENTILE, INPUT_HIGH_PERCENTILE])
    low = float(low)
    high = float(high)
    if (not np.isfinite(low)) or (not np.isfinite(high)) or high <= low:
        return np.zeros_like(data, dtype=np.float32)

    normalized = (data - low) / (high - low)
    normalized = np.clip(normalized, 0.0, 1.0)
    normalized = np.where(finite_mask, normalized, 0.0)
    return normalized.astype(np.float32, copy=False)


def _normalize_enhanced_unit(image: np.ndarray) -> np.ndarray:
    """Normalize enhanced image to [0, 1] with robust background suppression."""
    data = np.asarray(image, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not np.any(finite_mask):
        return np.zeros_like(data, dtype=np.float32)

    valid = data[finite_mask]
    background = float(np.nanmedian(valid))
    sigma = 1.4826 * float(np.nanmedian(np.abs(valid - background)))

    if (not np.isfinite(sigma)) or sigma <= EPS:
        sigma = float(np.nanstd(valid))
        if (not np.isfinite(sigma)) or sigma <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    # Gate out most background fluctuations before scaling.
    noise_floor = background + (NOISE_FLOOR_SIGMA * sigma)
    residual = np.clip(data - noise_floor, 0.0, None)
    residual = np.where(finite_mask, residual, 0.0)

    positive = residual[residual > 0.0]
    if positive.size == 0:
        return np.zeros_like(data, dtype=np.float32)
    high = float(np.nanpercentile(positive, SIGNAL_SCALE_QUANTILE))
    if (not np.isfinite(high)) or high <= EPS:
        high = float(np.nanmax(positive))
        if (not np.isfinite(high)) or high <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    scale = max(high, MIN_SCALE_SIGMA * sigma, EPS)
    normalized = np.clip(residual / scale, 0.0, 1.0)
    return normalized.astype(np.float32, copy=False)


def _clamp_spot_size(value: float) -> float:
    """Clamp spot-size control to a safe positive range."""
    return float(np.clip(value, MIN_SPOT_SIZE, MAX_SPOT_SIZE))


def _spot_size_to_detection_scale(spot_size: float) -> float:
    """Convert user spot-size control to internal image scaling.

    spot_size > 1 means detect larger spots (zoom out input),
    spot_size < 1 means detect smaller spots (zoom in input).
    """
    return 1.0 / _clamp_spot_size(spot_size)


def _scale_image_for_detection(
    image: np.ndarray,
    scale: float,
) -> np.ndarray:
    """Rescale image before U-FISH inference.

    For 3D stacks, scale is applied to y/x only and z is preserved.
    """
    if abs(scale - 1.0) < 1e-6:
        return image.astype(np.float32, copy=False)
    if image.ndim == 2:
        target_shape = tuple(max(1, int(round(dim * scale))) for dim in image.shape)
    else:
        target_shape = (
            image.shape[0],
            max(1, int(round(image.shape[1] * scale))),
            max(1, int(round(image.shape[2] * scale))),
        )
    zoom_factors = tuple(
        target / source for target, source in zip(target_shape, image.shape)
    )
    scaled = ndi.zoom(
        image.astype(np.float32, copy=False),
        zoom=zoom_factors,
        order=1,
        mode="nearest",
    )
    return scaled.astype(np.float32, copy=False)


def _fit_to_shape(array: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    """Crop/pad array to exactly match target shape."""
    if array.shape == target_shape:
        return array

    src_slices = tuple(slice(0, min(src, tgt)) for src, tgt in zip(array.shape, target_shape))
    cropped = array[src_slices]
    if cropped.shape == target_shape:
        return cropped

    fitted = np.zeros(target_shape, dtype=array.dtype)
    dst_slices = tuple(slice(0, dim) for dim in cropped.shape)
    fitted[dst_slices] = cropped
    return fitted

def _restore_image_to_input_scale(
    image: np.ndarray,
    original_shape: tuple[int, ...],
) -> np.ndarray:
    """Restore floating-point image to original input scale."""
    if image.shape == original_shape:
        return image.astype(np.float32, copy=False)
    zoom_factors = tuple(
        target / source for target, source in zip(original_shape, image.shape)
    )
    restored = ndi.zoom(
        image.astype(np.float32, copy=False),
        zoom=zoom_factors,
        order=1,
        mode="nearest",
    )
    restored = _fit_to_shape(restored, original_shape)
    return restored.astype(np.float32, copy=False)


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
    use_laplace: bool = True,
) -> np.ndarray:
    """Build marker labels from U-FISH local maxima calls."""
    connectivity = max(1, min(2, enhanced.ndim))
    response = (
        laplace(enhanced.astype(np.float32, copy=False))
        if use_laplace
        else np.asarray(enhanced, dtype=np.float32)
    )
    mask = local_maxima(response, connectivity=connectivity)
    mask = mask & (response > threshold)

    markers = np.zeros(enhanced.shape, dtype=np.int32)
    coords = np.argwhere(mask)
    if coords.size == 0:
        return markers

    max_indices = np.asarray(enhanced.shape) - 1
    coords = np.clip(coords, 0, max_indices)
    markers[tuple(coords.T)] = 1

    structure = ndi.generate_binary_structure(enhanced.ndim, 1)
    marker_labels, _num = ndi.label(markers > 0, structure=structure)
    return marker_labels.astype(np.int32, copy=False)


def _segment_from_markers(
    enhanced: np.ndarray,
    markers: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Run watershed from local-maxima markers inside threshold foreground."""
    foreground = enhanced > threshold
    if not np.any(foreground):
        return np.zeros_like(enhanced, dtype=np.int32)

    seeded_markers = markers * foreground.astype(np.int32, copy=False)
    if not np.any(seeded_markers > 0):
        return np.zeros_like(enhanced, dtype=np.int32)

    labels = watershed(
        -enhanced.astype(np.float32, copy=False),
        markers=seeded_markers,
        mask=foreground,
    )
    return labels.astype(np.int32, copy=False)


class UFishDetector(SenoQuantSpotDetector):
    """Spot detector using U-FISH local maxima and watershed expansion."""

    def __init__(self, models_root=None) -> None:
        super().__init__("ufish", models_root=models_root)

    def run(self, **kwargs) -> dict:
        """Run U-FISH seeded watershed and return instance labels."""
        layer = kwargs.get("layer")
        if layer is None:
            return {"mask": None, "points": None}
        if getattr(layer, "rgb", False):
            raise ValueError("U-FISH detector requires single-channel images.")

        settings = kwargs.get("settings", {}) or {}
        threshold = _clamp_threshold(float(settings.get("threshold", DEFAULT_THRESHOLD)))
        use_laplace = USE_LAPLACE_FOR_PEAKS
        denoise_enabled = DEFAULT_DENOISE_ENABLED
        spot_size = _clamp_spot_size(
            float(settings.get("spot_size", DEFAULT_SPOT_SIZE))
        )
        scale = _spot_size_to_detection_scale(spot_size)

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("U-FISH detector expects 2D images or 3D stacks.")

        data = _normalize_input_percentile(data)
        denoised = wavelet_denoise_input(
            data,
            enabled=denoise_enabled,
        )
        scaled_input = _scale_image_for_detection(denoised, scale)

        enhanced_raw = enhance_image(
            np.asarray(scaled_input, dtype=np.float32),
            config=UFishConfig(),
        )
        enhanced_raw = np.asarray(enhanced_raw, dtype=np.float32)

        # Re-normalize after enhancement
        enhanced_normalized = _normalize_enhanced_unit(enhanced_raw)

        # Segment in original resolution to avoid blocky label upsampling artifacts.
        enhanced_for_seg = _restore_image_to_input_scale(
            enhanced_normalized,
            data.shape,
        )

        markers = _markers_from_local_maxima(
            enhanced_for_seg,
            threshold,
            use_laplace=use_laplace,
        )
        labels = _segment_from_markers(
            enhanced_for_seg,
            markers,
            threshold,
        )
        # debug_enhanced = _restore_image_to_input_scale(enhanced_raw, data.shape)
        # debug_enhanced_normalized = enhanced_for_seg
        return {
            "mask": labels,
            # "debug_images": {
            #     # "debug_normalized_image": normalized.astype(np.float32, copy=False),
            #     "debug_denoised_image": denoised.astype(np.float32, copy=False),
            #     "debug_enhanced_image": debug_enhanced,
            #     "debug_enhanced_image_normalized": debug_enhanced_normalized,
            # },
        }
