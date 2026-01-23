"""Empirically estimate receptive field and tiling overlap for ONNX models.

This module mirrors StarDist's empirical receptive-field estimation:
run the model once on a single-pixel impulse and once on zeros, then
measure the spatial support of the difference in the probability output.
The measured extents define the overlap needed to avoid tile boundary
artifacts in tiled prediction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from .divisibility import infer_div_by


def infer_receptive_field(
    model_path: str | Path,
    ndim: int | None = None,
    input_shape: tuple[int, ...] | None = None,
    eps: float = 0.0,
) -> tuple[tuple[int, int], ...]:
    """Estimate the receptive field via impulse response.

    This mirrors StarDist's empirical receptive-field estimation: run the model
    on an impulse image and on zeros, then find the spatial support of the
    difference.

    Parameters
    ----------
    model_path : str or pathlib.Path
        Path to the ONNX model file.
    ndim : int or None, optional
        Spatial dimensionality (2 or 3). If None, inferred from input rank.
    input_shape : tuple[int, ...] or None, optional
        Spatial shape for the probe input. If None, a power-of-two shape is
        chosen and adjusted to satisfy the inferred divisibility.
    eps : float, optional
        Threshold used to detect non-zero influence in the output. Default 0.0.

    Returns
    -------
    tuple[tuple[int, int], ...]
        Per-axis receptive field extents as (left, right) offsets from the
        center pixel/voxel in input coordinates.

    Notes
    -----
    - The probe uses an impulse (single 1.0) at the spatial center.
    - The probability output is selected by heuristics (last dim == 1).
    - Output is mapped back to input resolution using the inferred grid.
    """
    import onnxruntime as ort
    from scipy.ndimage import zoom

    model_path = Path(model_path)
    session = ort.InferenceSession(str(model_path))

    input_name = session.get_inputs()[0].name
    output_names = [out.name for out in session.get_outputs()]

    if ndim is None:
        ndim = _infer_ndim_from_input(session)

    if input_shape is None:
        # Choose a reasonable power-of-two probe size and round up to a
        # multiple of the inferred divisibility to avoid internal mismatches.
        base = 256 if ndim == 2 else 64
        div_by = infer_div_by(model_path, ndim=ndim)
        input_shape = tuple(_round_up(base, d) for d in div_by)

    if len(input_shape) != ndim:
        raise ValueError("input_shape must match ndim.")

    # Build impulse and zero inputs (NHWC/NDHWC).
    center = tuple(s // 2 for s in input_shape)
    x = np.zeros((1, *input_shape, 1), dtype=np.float32)
    z = np.zeros_like(x)
    x[(0, *center, 0)] = 1.0

    # Run the model and extract the probability output.
    y = _run_prob(session, output_names, input_name, x, ndim)
    y0 = _run_prob(session, output_names, input_name, z, ndim)

    # Infer grid from input/output shapes (input / output per axis).
    grid = tuple(
        max(1, int(round(si / so))) for si, so in zip(input_shape, y.shape)
    )
    y = zoom(y, grid, order=0)
    y0 = zoom(y0, grid, order=0)

    # Measure where the response differs from zero.
    diff = np.abs(y - y0) > eps
    indices = np.where(diff)
    if any(len(i) == 0 for i in indices):
        raise RuntimeError("Failed to detect receptive field; try a larger input_shape.")

    return tuple((c - int(np.min(i)), int(np.max(i)) - c) for c, i in zip(center, indices))


def recommend_tile_overlap(
    model_path: str | Path,
    ndim: int | None = None,
    input_shape: tuple[int, ...] | None = None,
    eps: float = 0.0,
) -> tuple[int, ...]:
    """Return recommended tile overlap per axis from empirical RF.

    Parameters
    ----------
    model_path : str or pathlib.Path
        Path to the ONNX model file.
    ndim : int or None, optional
        Spatial dimensionality (2 or 3). If None, inferred from input rank.
    input_shape : tuple[int, ...] or None, optional
        Spatial probe input shape. If None, a default shape is used.
    eps : float, optional
        Threshold used to detect non-zero influence in the output.

    Returns
    -------
    tuple[int, ...]
        Per-axis overlap in input pixels.
    """
    rf = infer_receptive_field(
        model_path=model_path,
        ndim=ndim,
        input_shape=input_shape,
        eps=eps,
    )
    return tuple(max(pair) for pair in rf)


def _run_prob(session, output_names, input_name, input_tensor, ndim: int) -> np.ndarray:
    """Run the ONNX model and return the probability output in spatial layout."""
    outputs = session.run(output_names, {input_name: input_tensor})
    prob = _select_prob_output(outputs)
    prob = _to_spatial(prob, ndim)
    return prob


def _select_prob_output(outputs: list[np.ndarray]) -> np.ndarray:
    """Pick the probability output from ONNX outputs."""
    for arr in outputs:
        if arr.ndim >= 4 and arr.shape[-1] == 1:
            return arr
    return outputs[0]


def _to_spatial(prob: np.ndarray, ndim: int) -> np.ndarray:
    """Convert a batched prob tensor into spatial layout (YX/ZYX)."""
    if ndim == 2:
        if prob.ndim == 4 and prob.shape[-1] == 1:
            return prob[0, ..., 0]
        if prob.ndim == 4 and prob.shape[1] == 1:
            return prob[0, 0, ...]
    if ndim == 3:
        if prob.ndim == 5 and prob.shape[-1] == 1:
            return prob[0, ..., 0]
        if prob.ndim == 5 and prob.shape[1] == 1:
            return prob[0, 0, ...]
    raise ValueError("Unsupported prob output layout.")


def _infer_ndim_from_input(session) -> int:
    """Infer spatial dimensionality from ONNX session input rank."""
    shape = session.get_inputs()[0].shape
    if len(shape) == 4:
        return 2
    if len(shape) == 5:
        return 3
    raise ValueError(f"Unsupported input rank {len(shape)}.")


def _round_up(value: int, multiple: int) -> int:
    """Round up ``value`` to the next multiple."""
    if multiple <= 0:
        return value
    return int(np.ceil(value / multiple) * multiple)
