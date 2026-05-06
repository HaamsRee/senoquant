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


def _expand_component_slice(
    component_slice: tuple[slice, ...],
    shape: tuple[int, ...],
) -> tuple[tuple[slice, ...], tuple[slice, ...]]:
    """Return an expanded component ROI plus its inner component slice.

    The expanded ROI is clipped to the image bounds and includes a one-voxel
    margin around the component when possible. The inner slice maps arrays
    computed on the expanded ROI back to the original component bounding box.

    Parameters
    ----------
    component_slice
        Tight bounding-box slice returned by ``ndi.find_objects`` for one
        connected component.
    shape
        Full image shape used to clip the expanded ROI at image boundaries.

    Returns
    -------
    tuple of tuple of slice
        ``(expanded_slice, inner_slice)``. ``expanded_slice`` indexes the full
        image, while ``inner_slice`` indexes the original tight component bounds
        within arrays computed on ``expanded_slice``.
    """
    expanded_slices: list[slice] = []
    inner_slices: list[slice] = []
    for axis_slice, axis_size in zip(component_slice, shape):
        start = max(0, int(axis_slice.start) - 1)
        stop = min(axis_size, int(axis_slice.stop) + 1)
        expanded_slices.append(slice(start, stop))
        inner_slices.append(
            slice(
                int(axis_slice.start) - start,
                int(axis_slice.stop) - start,
            )
        )
    return tuple(expanded_slices), tuple(inner_slices)


def _normalized_component_distance_local_edt(
    component_labels: np.ndarray,
    valid_component_mask: np.ndarray,
) -> np.ndarray:
    """Return exact per-component EDT normalized to each component's max distance.

    This preserves the old full-volume EDT semantics while limiting the expensive
    transform to one connected-component ROI at a time. Voxels outside
    ``valid_component_mask`` are left at zero, even when they belong to a labeled
    foreground component.

    Parameters
    ----------
    component_labels
        Connected-component labels for the thresholded foreground. Label ``0`` is
        background; positive labels identify foreground components.
    valid_component_mask
        Boolean mask of foreground voxels that should receive normalized distance
        values, typically finite foreground voxels from the reference image.

    Returns
    -------
    np.ndarray
        Float32 array with the same shape as ``component_labels``. Valid
        foreground voxels contain EDT divided by their component's maximum EDT;
        all other voxels are zero.
    """
    normalized_distance = np.zeros(component_labels.shape, dtype=np.float32)
    component_slices = ndi.find_objects(component_labels)
    for label_id, component_slice in enumerate(component_slices, start=1):
        if component_slice is None:
            continue

        # Expand by one voxel so border distances see neighboring background
        # instead of treating the tight ROI edge as out-of-bounds foreground.
        expanded_slice, inner_slice = _expand_component_slice(
            component_slice,
            component_labels.shape,
        )

        # Compute exact EDT only for this component's local ROI. Other labels in
        # the expanded box become background for this component.
        roi_labels = component_labels[expanded_slice]
        roi_mask = roi_labels == label_id
        if not np.any(roi_mask):
            continue

        roi_distance = ndi.distance_transform_edt(roi_mask)

        # Map the expanded ROI distances back to the original tight component
        # bounds, then normalize by that component's maximum distance.
        component_mask = component_labels[component_slice] == label_id
        if not np.any(component_mask):
            continue

        component_distance = roi_distance[inner_slice]
        max_distance = float(component_distance[component_mask].max())
        if (not np.isfinite(max_distance)) or max_distance <= EPS:
            continue

        valid_mask = component_mask & valid_component_mask[component_slice]
        if not np.any(valid_mask):
            continue

        # Keep this as a view; chained indexing would write into a temporary.
        distance_view = normalized_distance[component_slice]
        distance_view[valid_mask] = (
            component_distance[valid_mask] / max(max_distance, EPS)
        )

    return normalized_distance


def _markers_from_local_maxima(
    enhanced: np.ndarray,
    threshold: float,
    *,
    reference_image: np.ndarray | None = None,
    use_laplace: bool = USE_LAPLACE_FOR_PEAKS,
) -> np.ndarray:
    """Build watershed seed markers from filtered local maxima.

    ``enhanced`` defines the thresholded foreground. ``reference_image`` can be
    supplied when peak scoring should use a different intensity image than the
    enhanced foreground response. Returned values are connected marker labels,
    not final watershed instance labels.

    Parameters
    ----------
    enhanced
        Enhanced image used to define the thresholded foreground mask.
    threshold
        Foreground threshold applied to ``enhanced``.
    reference_image
        Optional image used for peak scoring and prominence checks. If omitted,
        ``enhanced`` is used.
    use_laplace
        Whether to score local maxima on the Laplacian response of the reference
        image instead of the reference intensities directly.

    Returns
    -------
    np.ndarray
        Int32 connected marker labels. Background and rejected maxima are zero.
    """
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

    # The foreground mask comes from the enhanced top-hat image, while the
    # optional reference image scores candidate peak intensity/prominence.
    valid_component_mask = foreground & np.isfinite(reference_float)

    # Bias local-maxima detection toward component centers without allocating a
    # full-volume float64 EDT. The helper preserves exact EDT normalization by
    # processing each connected component in an expanded local ROI.
    normalized_component_distance = _normalized_component_distance_local_edt(
        component_labels,
        valid_component_mask,
    )

    # Component-center weighting breaks ties inside plateaus and suppresses
    # boundary peaks in broad foreground components.
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

    # Scale peak intensity relative to bright finite foreground, not the whole
    # image, so sparse stacks are not dominated by background zeros.
    intensity_scale = float(np.nanpercentile(valid, 99.5))
    if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
        intensity_scale = float(np.nanmax(valid))
        if (not np.isfinite(intensity_scale)) or intensity_scale <= EPS:
            return np.zeros(enhanced_float.shape, dtype=np.int32)

    relative_intensity = np.zeros_like(reference_float, dtype=np.float32)
    relative_intensity[valid_component_mask] = (
        reference_float[valid_component_mask] / max(intensity_scale, EPS)
    )

    # Require each marker to stand out from its immediate neighborhood.
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
    """Run watershed from local-maxima markers inside threshold foreground.

    Marker labels are first masked back to the thresholded foreground so seeds
    outside the current foreground cannot create instances. Returns int32
    watershed labels with zero background.

    Parameters
    ----------
    enhanced
        Enhanced image used as the watershed elevation image and thresholded
        foreground mask.
    markers
        Connected seed marker labels, usually from ``_markers_from_local_maxima``.
    threshold
        Foreground threshold applied to ``enhanced``.

    Returns
    -------
    np.ndarray
        Int32 watershed instance labels with zero background.
    """
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
