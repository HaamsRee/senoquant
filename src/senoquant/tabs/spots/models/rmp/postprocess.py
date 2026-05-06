"""Postprocessing helpers for RMP top-hat outputs."""

from __future__ import annotations

import numpy as np
from skimage.filters import threshold_otsu

from .anisotropy import _spot_call_with_anisotropy_correction
from .config import RMPSettings
from .normalization import _clamp_threshold, _normalize_top_hat_unit


def _postprocess_top_hat(
    top_hat: np.ndarray,
    config: RMPSettings,
    *,
    reference_image: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply normalization, thresholding, marker extraction, and watershed."""
    top_hat_normalized = _normalize_top_hat_unit(top_hat)
    reference = (
        np.asarray(reference_image, dtype=np.float32)
        if reference_image is not None
        else top_hat_normalized
    )
    if reference.shape != top_hat_normalized.shape:
        raise ValueError("Reference image shape must match top-hat shape.")
    threshold = (
        _clamp_threshold(float(threshold_otsu(top_hat_normalized)))
        if config.auto_threshold
        else config.manual_threshold
    )
    labels = _spot_call_with_anisotropy_correction(
        top_hat_normalized,
        threshold,
        reference_image=reference,
    )
    return labels, top_hat_normalized
