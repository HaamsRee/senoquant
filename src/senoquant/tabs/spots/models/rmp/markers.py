"""Marker extraction and watershed segmentation for RMP outputs."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import laplace
from skimage.morphology import local_maxima
from skimage.segmentation import watershed

from .config import (
    EPS,
    PEAK_COMPONENT_DISTANCE_WEIGHT,
    PEAK_MIN_COMPONENT_DISTANCE_RATIO,
    PEAK_RELATIVE_INTENSITY_MIN,
    PEAK_RELATIVE_PROMINENCE_MIN,
    USE_LAPLACE_FOR_PEAKS,
)


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
    *,
    reference_image: np.ndarray | None = None,
    use_laplace: bool = USE_LAPLACE_FOR_PEAKS,
) -> np.ndarray:
    """Build marker labels from reference-image local maxima inside enhanced mask."""
    connectivity = max(1, min(2, enhanced.ndim))
    enhanced_float = np.asarray(enhanced, dtype=np.float32)
    reference_float = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else enhanced_float
    )
    if reference_float.shape != enhanced_float.shape:
        raise ValueError("Reference image shape must match enhanced image shape.")
    response = laplace(reference_float) if use_laplace else reference_float
    foreground = enhanced_float > threshold
    if not np.any(foreground):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    structure = ndi.generate_binary_structure(enhanced_float.ndim, 1)
    component_labels, num_components = ndi.label(foreground, structure=structure)
    if num_components == 0:
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    distance_to_boundary = ndi.distance_transform_edt(foreground)
    label_ids = np.arange(num_components + 1, dtype=np.int32)
    max_distance_by_label = np.asarray(
        ndi.maximum(
            distance_to_boundary,
            labels=component_labels,
            index=label_ids,
        ),
        dtype=np.float32,
    )

    component_scale = max_distance_by_label[component_labels]

    normalized_component_distance = np.zeros_like(response, dtype=np.float32)
    valid_component_mask = foreground & np.isfinite(reference_float)
    normalized_component_distance[valid_component_mask] = (
        distance_to_boundary[valid_component_mask]
        / np.maximum(component_scale[valid_component_mask], EPS)
    )

    weighted_response = response * (
        1.0 + (PEAK_COMPONENT_DISTANCE_WEIGHT * normalized_component_distance)
    )
    mask = local_maxima(weighted_response, connectivity=connectivity)
    mask = mask & foreground
    mask = mask & (
        normalized_component_distance >= PEAK_MIN_COMPONENT_DISTANCE_RATIO
    )
    if not np.any(mask):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    valid = reference_float[valid_component_mask]
    if valid.size == 0:
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    intensity_scale = float(np.nanpercentile(valid, 99.5))
    if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
        intensity_scale = float(np.nanmax(valid))
        if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
            return np.zeros(enhanced_float.shape, dtype=np.int32)

    relative_intensity = np.zeros_like(reference_float, dtype=np.float32)
    relative_intensity[valid_component_mask] = (
        reference_float[valid_component_mask] / max(intensity_scale, EPS)
    )

    prominence_floor = ndi.minimum_filter(reference_float, size=3, mode="nearest")
    relative_prominence = (reference_float - prominence_floor) / np.maximum(
        reference_float,
        EPS,
    )
    relative_prominence = np.clip(relative_prominence, 0.0, None)

    mask = mask & valid_component_mask
    mask = mask & (relative_intensity >= PEAK_RELATIVE_INTENSITY_MIN)
    mask = mask & (relative_prominence >= PEAK_RELATIVE_PROMINENCE_MIN)
    if not np.any(mask):
        return np.zeros(enhanced_float.shape, dtype=np.int32)

    markers = np.zeros(enhanced_float.shape, dtype=np.int32)
    coords = np.argwhere(mask)
    if coords.size == 0:
        return markers

    max_indices = np.asarray(enhanced_float.shape) - 1
    coords = np.clip(coords, 0, max_indices)
    markers[tuple(coords.T)] = 1

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
