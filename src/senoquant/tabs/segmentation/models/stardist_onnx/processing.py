"""Pre/post processing helpers for StarDist ONNX."""

from __future__ import annotations

import numpy as np


def infer_image_axes(image: np.ndarray) -> str:
    """Return the standard axes string for a 2D/3D image."""
    if image.ndim == 2:
        return "YX"
    if image.ndim == 3:
        return "ZYX"
    raise ValueError("StarDist ONNX expects 2D or 3D image data.")


def normalize_percentile(
    image: np.ndarray,
    pmin: float = 1.0,
    pmax: float = 99.8,
    eps: float = 1e-6,
) -> np.ndarray:
    """Normalize an image using percentile scaling."""
    if pmax <= pmin:
        raise ValueError("Percentile max must be greater than min.")
    lo = np.percentile(image, pmin)
    hi = np.percentile(image, pmax)
    scale = hi - lo
    if scale < eps:
        return np.zeros_like(image, dtype=np.float32)
    normalized = (image - lo) / scale
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def squeeze_batch(data: np.ndarray) -> np.ndarray:
    """Remove a leading batch axis if present."""
    if data.ndim > 0 and data.shape[0] == 1:
        return data[0]
    return data


def add_axes(
    data: np.ndarray,
    source_axes: str,
    target_axes: str,
) -> np.ndarray:
    """Add missing singleton axes and reorder to target axes."""
    _validate_axes(source_axes)
    _validate_axes(target_axes)

    axes = list(source_axes)
    for axis in target_axes:
        if axis not in axes:
            data = np.expand_dims(data, axis=-1)
            axes.append(axis)

    _validate_axes("".join(axes))
    permutation = [axes.index(axis) for axis in target_axes]
    return np.transpose(data, permutation)


def drop_axes(
    data: np.ndarray,
    source_axes: str,
    target_axes: str,
) -> np.ndarray:
    """Drop singleton axes and reorder to target axes."""
    _validate_axes(source_axes)
    _validate_axes(target_axes)

    axes = list(source_axes)
    for axis in list(axes):
        if axis not in target_axes:
            idx = axes.index(axis)
            if data.shape[idx] != 1:
                raise ValueError(
                    f"Cannot drop non-singleton axis '{axis}' from {source_axes}."
                )
            data = np.squeeze(data, axis=idx)
            axes.pop(idx)

    if set(axes) != set(target_axes):
        raise ValueError(
            f"Axes mismatch after dropping. Have {axes}, need {target_axes}."
        )
    permutation = [axes.index(axis) for axis in target_axes]
    return np.transpose(data, permutation)


def _validate_axes(axes: str) -> None:
    if len(set(axes)) != len(axes):
        raise ValueError(f"Axes string contains duplicates: {axes}.")
