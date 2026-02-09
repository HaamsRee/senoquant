"""Shared denoising helpers for spot detectors."""

from __future__ import annotations

import numpy as np
from skimage.restoration import denoise_wavelet


def wavelet_denoise_input(
    image: np.ndarray,
    *,
    enabled: bool,
) -> np.ndarray:
    """Optionally denoise image with a wavelet denoiser."""
    if not enabled:
        return image.astype(np.float32, copy=False)
    data = image.astype(np.float32, copy=False)
    denoised = denoise_wavelet(
        data,
        method="BayesShrink",
        mode="soft",
        rescale_sigma=True,
        channel_axis=None,
    )
    return np.asarray(denoised, dtype=np.float32)
