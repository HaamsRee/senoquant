"""Empirically infer valid spatial sizes for ONNX model inputs.

This module probes the ONNX runtime by running the model on small inputs and
recording which spatial sizes succeed. It then summarizes valid sizes as
periodic residues (e.g., sizes of the form ``16k`` or ``16k+1``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class ValidSizePattern:
    """Periodic validity pattern for a single spatial axis.

    Attributes
    ----------
    period : int
        Periodicity for valid sizes.
    residues : tuple[int, ...]
        Allowed ``size % period`` residues.
    min_valid : int
        Smallest observed valid size.
    """

    period: int
    residues: tuple[int, ...]
    min_valid: int


def infer_valid_size_patterns(
    session,
    input_name: str,
    output_names: Iterable[str],
    input_layout: str,
    ndim: int,
    max_probe: int = 64,
) -> list[ValidSizePattern]:
    """Probe ONNX execution to infer valid size residues per axis.

    Parameters
    ----------
    session : onnxruntime.InferenceSession
        ONNX Runtime session used to execute the model.
    input_name : str
        Name of the ONNX input tensor.
    output_names : Iterable[str]
        Output tensor names to request during inference.
    input_layout : str
        Input layout string (e.g., ``"NHWC"`` or ``"NDHWC"``).
    ndim : int
        Spatial dimensionality (2 or 3).
    max_probe : int, optional
        Maximum size to probe per axis. Default is 64.

    Returns
    -------
    list[ValidSizePattern]
        One entry per axis describing periodic valid size residues.

    Raises
    ------
    RuntimeError
        If no valid sizes can be found within the probe range.
    """
    if ndim not in (2, 3):
        raise ValueError("ndim must be 2 or 3.")

    output_names = list(output_names)

    base = _find_valid_base(
        session, input_name, output_names, input_layout, ndim, max_probe
    )

    patterns: list[ValidSizePattern] = []
    any_valid = False
    for axis in range(ndim):
        valid = []
        for size in range(1, max_probe + 1):
            shape = [base] * ndim
            shape[axis] = size
            if _try_run(session, input_name, output_names, input_layout, shape):
                valid.append(size)
        if not valid:
            patterns.append(ValidSizePattern(period=1, residues=(0,), min_valid=1))
            continue
        any_valid = True
        period, residues = _infer_period_and_residues(valid, max_probe)
        patterns.append(
            ValidSizePattern(
                period=int(period),
                residues=tuple(int(r) for r in residues),
                min_valid=int(min(valid)),
            )
        )

    if not any_valid:
        raise RuntimeError(
            f"No valid sizes found within 1..{max_probe} for any axis."
        )
    return patterns


def infer_valid_size_patterns_from_path(
    model_path,
    input_layout: str,
    ndim: int,
    max_probe: int = 64,
) -> list[ValidSizePattern]:
    """Probe valid sizes using a temporary, quiet ONNX session.

    Parameters
    ----------
    model_path : str or pathlib.Path
        Path to the ONNX model file.
    input_layout : str
        Input layout string (e.g., ``"NHWC"`` or ``"NDHWC"``).
    ndim : int
        Spatial dimensionality (2 or 3).
    max_probe : int, optional
        Maximum size to probe per axis. Default is 64.

    Returns
    -------
    list[ValidSizePattern]
        One entry per axis describing periodic valid size residues.
    """
    import onnxruntime as ort

    sess_options = ort.SessionOptions()
    # Suppress ORT error logs during probe failures.
    sess_options.log_severity_level = 4
    session = ort.InferenceSession(str(model_path), sess_options=sess_options)
    input_name = session.get_inputs()[0].name
    output_names = [o.name for o in session.get_outputs()]
    return infer_valid_size_patterns(
        session,
        input_name,
        output_names,
        input_layout,
        ndim,
        max_probe=max_probe,
    )


def _find_valid_base(
    session,
    input_name: str,
    output_names: list[str],
    input_layout: str,
    ndim: int,
    max_probe: int,
) -> int:
    """Return the smallest symmetric size that executes successfully."""
    for size in range(1, max_probe + 1):
        shape = [size] * ndim
        if _try_run(session, input_name, output_names, input_layout, shape):
            return size
    raise RuntimeError("Failed to find any valid base size for probing.")


def _try_run(
    session,
    input_name: str,
    output_names: list[str],
    input_layout: str,
    spatial_shape: list[int],
) -> bool:
    """Return True if the model runs on the given spatial shape."""
    if input_layout in ("NHWC", "NDHWC"):
        input_tensor = np.zeros((1, *spatial_shape, 1), dtype=np.float32)
    elif input_layout in ("NCHW", "NCDHW"):
        input_tensor = np.zeros((1, 1, *spatial_shape), dtype=np.float32)
    else:
        raise ValueError(f"Unsupported input layout {input_layout}.")
    try:
        session.run(list(output_names), {input_name: input_tensor})
    except Exception:
        return False
    return True


def _infer_period_and_residues(
    valid_sizes: list[int], max_probe: int
) -> tuple[int, list[int]]:
    """Infer periodicity and residue set for valid sizes."""
    valid_set = set(valid_sizes)
    if not valid_set:
        return 1, [0]

    min_valid = min(valid_set)
    for period in range(1, max_probe + 1):
        residues = {v % period for v in valid_set}
        ok = True
        for size in range(min_valid, max_probe + 1):
            if (size % period in residues) != (size in valid_set):
                ok = False
                break
        if ok:
            return period, sorted(residues)

    if len(valid_sizes) < 2:
        return max(1, valid_sizes[0]), [valid_sizes[0] % max(1, valid_sizes[0])]

    diffs = [b - a for a, b in zip(valid_sizes, valid_sizes[1:]) if b > a]
    period = diffs[0]
    for d in diffs[1:]:
        period = math.gcd(period, d)
    residues = sorted({v % period for v in valid_set})
    return max(1, period), residues


def snap_size(size: int, pattern: ValidSizePattern) -> int:
    """Adjust a size to the nearest valid residue at or below ``size``.

    Parameters
    ----------
    size : int
        Proposed size.
    pattern : ValidSizePattern
        Valid size pattern for the axis.

    Returns
    -------
    int
        Snapped valid size.
    """
    period = max(1, int(pattern.period))
    residues = set(int(r) for r in pattern.residues)
    min_valid = int(pattern.min_valid)
    if size <= min_valid:
        return min_valid
    for delta in range(period + 1):
        candidate = size - delta
        if candidate < min_valid:
            break
        if candidate % period in residues:
            return candidate
    candidate = size
    while candidate % period not in residues:
        candidate += 1
    return candidate


def snap_shape(
    shape: Sequence[int],
    patterns: Sequence[ValidSizePattern],
    *,
    skip_axes: Sequence[int] = (),
) -> tuple[int, ...]:
    """Snap each axis of a shape to the nearest valid size.

    Parameters
    ----------
    shape : Sequence[int]
        Proposed spatial shape.
    patterns : Sequence[ValidSizePattern]
        Per-axis valid size patterns.
    skip_axes : Sequence[int], optional
        Axes to leave unchanged (e.g., skip Z for 3D models).

    Returns
    -------
    tuple[int, ...]
        Snapped spatial shape.
    """
    snapped = []
    for axis, size in enumerate(shape):
        if axis in skip_axes:
            snapped.append(int(size))
            continue
        snapped.append(snap_size(int(size), patterns[axis]))
    return tuple(snapped)
