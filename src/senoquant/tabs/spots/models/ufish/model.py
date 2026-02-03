"""U-FISH local-maxima seeded watershed detector."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import laplace
from skimage.morphology import local_maxima
from skimage.segmentation import watershed

from ..base import SenoQuantSpotDetector
from senoquant.utils import layer_data_asarray
from senoquant.tabs.spots.ufish_utils import UFishConfig, enhance_image


DEFAULT_THRESHOLD = 0.5


def _clamp_threshold(value: float) -> float:
    """Clamp threshold to the inclusive [0.0, 1.0] range."""
    return float(np.clip(value, 0.0, 1.0))


def _normalize_unit(image: np.ndarray) -> np.ndarray:
    """Normalize to float32 in [0, 1] using 0.5/99.5 percentiles."""
    data = np.asarray(image, dtype=np.float32)
    low, high = np.nanpercentile(data, [0.5, 99.5])
    low = float(low)
    high = float(high)
    if high <= low:
        return np.zeros_like(data, dtype=np.float32)
    normalized = (data - low) / (high - low)
    return np.clip(normalized, 0.0, 1.0).astype(np.float32, copy=False)


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Build marker labels from U-FISH local maxima calls."""
    connectivity = max(1, min(2, enhanced.ndim))
    enhanced_lap = laplace(enhanced)
    mask = local_maxima(enhanced_lap, connectivity=connectivity)
    mask = mask & (enhanced_lap > threshold)

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

        data = layer_data_asarray(layer)
        if data.ndim not in (2, 3):
            raise ValueError("U-FISH detector expects 2D images or 3D stacks.")
        enhanced = enhance_image(np.asarray(data, dtype=np.float32), config=UFishConfig())
        enhanced = np.asarray(enhanced, dtype=np.float32)
        enhanced = _normalize_unit(enhanced)

        markers = _markers_from_local_maxima(enhanced, threshold)
        labels = _segment_from_markers(enhanced, markers, threshold)
        return {"mask": labels}
