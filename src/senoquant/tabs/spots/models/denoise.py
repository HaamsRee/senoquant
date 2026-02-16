"""Shared denoising helpers for spot detectors."""

from __future__ import annotations

import numpy as np
from skimage.restoration import denoise_bilateral, denoise_wavelet


def wavelet_denoise_input(
    image: np.ndarray,
    *,
    enabled: bool,
    sigma: float | None = None,
) -> np.ndarray:
    """Optionally denoise image with a wavelet denoiser."""
    if not enabled:
        return image.astype(np.float32, copy=False)
    data = image.astype(np.float32, copy=False)
    sigma_value = None if sigma is None else float(sigma)
    if sigma_value is not None and sigma_value <= 0:
        sigma_value = None
    denoised = denoise_wavelet(
        data,
        sigma=sigma_value,
        method="BayesShrink",
        mode="soft",
        rescale_sigma=True,
        channel_axis=None,
    )
    return np.asarray(denoised, dtype=np.float32)


def bilateral_denoise_input(
    image: np.ndarray,
    *,
    enabled: bool,
    sigma_color: float = 0.12,
    sigma_spatial: float = 2.0,
) -> np.ndarray:
    """Optionally denoise image with bilateral filtering.

    Uses slice-wise filtering for 3D stacks to keep behavior predictable
    for z-first microscopy volumes.
    """
    data = image.astype(np.float32, copy=False)
    if not enabled:
        return data

    if data.ndim == 2:
        denoised = denoise_bilateral(
            data,
            sigma_color=float(sigma_color),
            sigma_spatial=float(sigma_spatial),
            channel_axis=None,
        )
        return np.asarray(denoised, dtype=np.float32)

    if data.ndim == 3:
        out = np.empty_like(data, dtype=np.float32)
        for z in range(data.shape[0]):
            out[z] = np.asarray(
                denoise_bilateral(
                    data[z],
                    sigma_color=float(sigma_color),
                    sigma_spatial=float(sigma_spatial),
                    channel_axis=None,
                ),
                dtype=np.float32,
            )
        return out

    return data
