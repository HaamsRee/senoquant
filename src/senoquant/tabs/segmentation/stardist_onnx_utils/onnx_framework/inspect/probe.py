"""Utilities for creating valid probe inputs for ONNX inspection."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .divisibility import infer_div_by
from .valid_sizes import infer_valid_size_patterns_from_path, snap_size


def make_probe_image(
    image: np.ndarray,
    *,
    model_path: Path | None = None,
    input_layout: str | None = None,
    div_by_cache: dict[Path, tuple[int, ...]] | None = None,
    valid_size_cache: dict[Path, list[object] | None] | None = None,
) -> np.ndarray:
    """Create a small probe image aligned with ONNX size constraints.

    Parameters
    ----------
    image : numpy.ndarray
        Input image array used to derive probe size.
    model_path : pathlib.Path or None, optional
        ONNX model path used for inspecting size constraints.
    input_layout : str or None, optional
        Model input layout (e.g., "NHWC", "NDHWC") used for size inspection.
    div_by_cache : dict or None, optional
        Cache for divisibility requirements keyed by model path.
    valid_size_cache : dict or None, optional
        Cache for valid size patterns keyed by model path.

    Returns
    -------
    numpy.ndarray
        Probe image padded/cropped to a valid spatial size.
    """
    target = 256 if image.ndim == 2 else 64
    probe_shape = []
    for dim in image.shape:
        size = min(dim, target)
        if size >= 16:
            size = size - (size % 16)
            if size == 0:
                size = min(dim, target)
        probe_shape.append(max(1, size))

    probe = image[tuple(slice(0, s) for s in probe_shape)]

    if model_path is None or input_layout is None:
        return probe

    patterns = None
    if valid_size_cache is not None:
        patterns = valid_size_cache.get(model_path)
    if patterns is None:
        try:
            patterns = infer_valid_size_patterns_from_path(
                model_path,
                input_layout,
                image.ndim,
            )
        except Exception:
            patterns = None
        if valid_size_cache is not None:
            valid_size_cache[model_path] = patterns

    div_by = None
    if div_by_cache is not None:
        div_by = div_by_cache.get(model_path)
    if div_by is None:
        try:
            div_by = infer_div_by(model_path, ndim=image.ndim)
        except Exception:
            div_by = None
        if div_by_cache is not None and div_by is not None:
            div_by_cache[model_path] = div_by

    desired = list(probe.shape)
    if patterns:
        desired = [
            max(1, snap_size(int(size), patterns[axis]))
            for axis, size in enumerate(desired)
        ]
    elif div_by:
        desired = [
            max(int(d), (int(size) // int(d)) * int(d)) if d else int(size)
            for size, d in zip(desired, div_by)
        ]

    desired = [max(1, int(size)) for size in desired]
    crop_slices = tuple(slice(0, min(s, d)) for s, d in zip(probe.shape, desired))
    probe = probe[crop_slices]
    pads = [(0, max(0, d - s)) for s, d in zip(probe.shape, desired)]
    if any(pad_after > 0 for _, pad_after in pads):
        probe = np.pad(probe, pads, mode="reflect")
    return probe