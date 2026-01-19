"""Thresholding helpers for marker features."""

from __future__ import annotations

import numpy as np
from skimage import filters

THRESHOLD_METHODS = {
    "Otsu": filters.threshold_otsu,
    "Yen": filters.threshold_yen,
    "Li": filters.threshold_li,
    "Isodata": filters.threshold_isodata,
    "Triangle": filters.threshold_triangle,
}


def compute_threshold(data, method: str) -> float:
    """Compute a threshold value for the given image data.

    Parameters
    ----------
    data : array-like
        Image data to threshold.
    method : str
        Thresholding method name.

    Returns
    -------
    float
        Threshold value.

    Raises
    ------
    ValueError
        If the method is unknown or the data is empty.
    """
    if method not in THRESHOLD_METHODS:
        raise ValueError(f"Unknown threshold method: {method}")
    array = np.asarray(data)
    if array.size == 0:
        raise ValueError("No image data available for thresholding.")
    if not np.isfinite(array).all():
        array = array[np.isfinite(array)]
    if array.size == 0:
        raise ValueError("No finite image data available for thresholding.")
    return float(THRESHOLD_METHODS[method](array))
