"""Shape, padding, and resampling helpers for the RMP detector."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def _fit_to_shape(array: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    """Crop/pad array to exactly match target shape."""
    if array.shape == target_shape:
        return array
    src_slices = tuple(
        slice(0, min(src, tgt)) for src, tgt in zip(array.shape, target_shape)
    )
    cropped = array[src_slices]
    if cropped.shape == target_shape:
        return cropped
    fitted = np.zeros(target_shape, dtype=array.dtype)
    dst_slices = tuple(slice(0, dim) for dim in cropped.shape)
    fitted[dst_slices] = cropped
    return fitted


def _zoom_to_shape(
    array: np.ndarray,
    target_shape: tuple[int, ...],
    *,
    order: int,
) -> np.ndarray:
    """Zoom an ndarray and force exact target shape via crop/pad."""
    if array.shape == target_shape:
        return array
    zoom_factors = tuple(
        (float(t) / float(s)) if s > 0 else 1.0
        for t, s in zip(target_shape, array.shape)
    )
    out = ndi.zoom(
        array,
        zoom=zoom_factors,
        order=order,
        mode="nearest",
        prefilter=order > 1,
    )
    return _fit_to_shape(out, target_shape)


def _pad_xy_to_chunk_multiple(
    image: np.ndarray,
    *,
    chunk_size: tuple[int, int],
) -> tuple[np.ndarray, tuple[slice, ...]]:
    """Pad trailing Y/X axes so tiled execution avoids tiny edge chunks."""
    data = np.asarray(image, dtype=np.float32)
    if data.ndim not in (2, 3):
        raise ValueError("Expected a 2D image or 3D stack for tiled padding.")

    chunk_y = max(1, int(chunk_size[0]))
    chunk_x = max(1, int(chunk_size[1]))
    pad_y = (-int(data.shape[-2])) % chunk_y
    pad_x = (-int(data.shape[-1])) % chunk_x
    crop_slices = tuple(slice(0, int(size)) for size in data.shape)
    if pad_y == 0 and pad_x == 0:
        return data, crop_slices

    pad_width = [(0, 0)] * data.ndim
    pad_width[-2] = (0, pad_y)
    pad_width[-1] = (0, pad_x)
    padded = np.pad(data, pad_width=tuple(pad_width), mode="reflect")
    return padded.astype(np.float32, copy=False), crop_slices
