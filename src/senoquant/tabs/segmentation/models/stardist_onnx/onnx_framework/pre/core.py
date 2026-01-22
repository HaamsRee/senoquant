"""Preprocessing helpers for ONNX StarDist inference.

These helpers mirror the high-level behavior of StarDist's preprocessing:
validate input dimensionality, optionally normalize, and pad to the grid
required by the network. The helpers assume single-channel images with
spatial axes ordered as YX (2D) or ZYX (3D).
"""

from __future__ import annotations

import numpy as np


def validate_image(image: np.ndarray) -> None:
    """Validate input image dimensionality.

    Parameters
    ----------
    image : numpy.ndarray
        Input image array expected to be 2D (YX) or 3D (ZYX) and single-channel.

    Raises
    ------
    ValueError
        If the input is not 2D or 3D.
    """
    if image.ndim not in (2, 3):
        raise ValueError("Input image must be 2D (YX) or 3D (ZYX).")


def normalize(
    image: np.ndarray,
    pmin: float = 1.0,
    pmax: float = 99.8,
    eps: float = 1e-6,
) -> np.ndarray:
    """Percentile normalize a single-channel image.

    Parameters
    ----------
    image : numpy.ndarray
        Input image to normalize.
    pmin : float, optional
        Lower percentile for normalization. Default is 1.0.
    pmax : float, optional
        Upper percentile for normalization. Default is 99.8.
    eps : float, optional
        Small constant to avoid division by zero. Default is 1e-6.

    Returns
    -------
    numpy.ndarray
        Normalized float32 image with values clipped to [0, 1].

    Raises
    ------
    ValueError
        If ``pmax`` is not greater than ``pmin``.
    """
    if pmax <= pmin:
        raise ValueError("pmax must be greater than pmin.")
    lo = np.percentile(image, pmin, keepdims=True)
    hi = np.percentile(image, pmax, keepdims=True)
    scale = hi - lo
    scale = np.where(scale < eps, 1.0, scale)
    normalized = (image - lo) / scale
    return np.clip(normalized, 0.0, 1.0).astype(np.float32)


def pad_to_multiple(
    image: np.ndarray,
    multiples: tuple[int, ...],
    mode: str = "reflect",
) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    """Pad each axis so its length is divisible by the corresponding multiple.

    Parameters
    ----------
    image : numpy.ndarray
        Input image (2D or 3D).
    multiples : tuple[int, ...]
        Per-axis divisibility constraints (e.g., the StarDist grid).
    mode : str, optional
        Padding mode passed to ``numpy.pad``. Default is "reflect".

    Returns
    -------
    numpy.ndarray
        Padded image as float32.
    tuple[tuple[int, int], ...]
        Padding applied per axis as (before, after) pairs. This implementation
        only pads at the end of each axis (before = 0).

    Raises
    ------
    ValueError
        If the multiples do not match the image dimensionality or contain
        non-positive values.
    """
    validate_image(image)
    if len(multiples) != image.ndim:
        raise ValueError("Multiples must match image dimensionality.")
    pads = []
    for dim, mult in zip(image.shape, multiples):
        if mult <= 0:
            raise ValueError("Multiples must be positive.")
        pad_after = (mult - (dim % mult)) % mult
        pads.append((0, pad_after))
    padded = np.pad(image, pads, mode=mode)
    return padded.astype(np.float32, copy=False), tuple(pads)


def unpad_to_shape(
    data: np.ndarray,
    pads: tuple[tuple[int, int], ...],
    scale: tuple[int, ...] | None = None,
) -> np.ndarray:
    """Crop padded output back to the unpadded shape (accounting for scale).

    Parameters
    ----------
    data : numpy.ndarray
        Output array to crop (e.g., probability or distance map).
    pads : tuple[tuple[int, int], ...]
        Padding applied to the input image as returned by ``pad_to_multiple``.
    scale : tuple[int, ...] or None, optional
        Per-axis scale factor between input and output spatial grids.
        For StarDist, this is typically the grid (e.g., (1, 1) or (2, 2)).
        If None, assumes scale 1 for all axes.

    Returns
    -------
    numpy.ndarray
        Cropped array with padding removed.

    Raises
    ------
    ValueError
        If scale dimensionality does not match pads, or if non-zero
        pre-padding is provided (this function assumes end-padding only).
    """
    if scale is None:
        scale = (1,) * len(pads)
    if len(scale) != len(pads):
        raise ValueError("Scale must match pad dimensionality.")
    slices = []
    for (before, after), mult in zip(pads, scale):
        if before != 0:
            raise ValueError("Only end-padding is supported.")
        if after >= mult:
            slices.append(slice(0, -(after // mult)))
        else:
            slices.append(slice(None))
    slices.extend([slice(None)] * (data.ndim - len(pads)))
    return data[tuple(slices)]
