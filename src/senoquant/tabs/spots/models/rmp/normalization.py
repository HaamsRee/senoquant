"""Normalization helpers for the RMP spot detector."""

from __future__ import annotations

import numpy as np

from .config import (
    EPS,
    MIN_SCALE_SIGMA,
    NOISE_FLOOR_SIGMA,
    SIGNAL_SCALE_QUANTILE,
)

try:
    import torch
except ImportError:  # pragma: no cover - optional dependency
    torch = None  # type: ignore[assignment]


def _normalization_torch_device() -> "torch.device":
    """Return the best available torch device for image normalization."""
    if torch is None:  # pragma: no cover - import guard
        raise ImportError("torch is required for RMP normalization.")
    if torch.cuda.is_available():
        return torch.device("cuda")
    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is not None and mps_backend.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _normalize_image(image: np.ndarray) -> np.ndarray:
    """Normalize an image to float32 in [0, 1]."""
    device = _normalization_torch_device()
    data = np.asarray(image, dtype=np.float32)
    assert torch is not None
    tensor = torch.as_tensor(data, dtype=torch.float32, device=device)
    min_val = tensor.amin()
    max_val = tensor.amax()
    if bool(max_val <= min_val):
        return np.zeros_like(data, dtype=np.float32)
    normalized = (tensor - min_val) / (max_val - min_val)
    normalized = normalized.clamp(0.0, 1.0)
    return normalized.detach().cpu().numpy().astype(np.float32, copy=False)


def _clamp_threshold(value: float) -> float:
    """Clamp threshold to the inclusive [0.0, 1.0] range."""
    return float(np.clip(value, 0.0, 1.0))


def _normalize_top_hat_unit(image: np.ndarray) -> np.ndarray:
    """Robust normalization for top-hat output."""
    data = np.asarray(image, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not np.any(finite_mask):
        return np.zeros_like(data, dtype=np.float32)

    valid = data[finite_mask]
    background = float(np.nanmedian(valid))
    sigma = 1.4826 * float(np.nanmedian(np.abs(valid - background)))

    if (not np.isfinite(sigma)) or sigma <= EPS:
        sigma = float(np.nanstd(valid))
        if (not np.isfinite(sigma)) or sigma <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    noise_floor = background + (NOISE_FLOOR_SIGMA * sigma)
    residual = np.clip(data - noise_floor, 0.0, None)
    residual = np.where(finite_mask, residual, 0.0)

    positive = residual[residual > 0.0]
    if positive.size == 0:
        return np.zeros_like(data, dtype=np.float32)
    high = float(np.nanpercentile(positive, SIGNAL_SCALE_QUANTILE))
    if (not np.isfinite(high)) or high <= EPS:
        high = float(np.nanmax(positive))
        if (not np.isfinite(high)) or high <= EPS:
            return np.zeros_like(data, dtype=np.float32)

    scale = max(high, MIN_SCALE_SIGMA * sigma, EPS)
    normalized = np.clip(residual / scale, 0.0, 1.0)
    return normalized.astype(np.float32, copy=False)
