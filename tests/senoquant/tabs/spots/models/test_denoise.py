"""Tests for shared spot-denoising utilities."""

from __future__ import annotations

import numpy as np

from senoquant.tabs.spots.models import denoise as denoise_model


def test_wavelet_denoise_input_disabled_returns_float32() -> None:
    """Return float32 data unchanged when denoising is disabled."""
    image = np.arange(12, dtype=np.float64).reshape(3, 4)
    out = denoise_model.wavelet_denoise_input(image, enabled=False)
    assert out.dtype == np.float32
    assert np.allclose(out, image.astype(np.float32))


def test_wavelet_denoise_input_3d_calls_wavelet_once(monkeypatch) -> None:
    """Apply a single wavelet call to 3D data (no per-z loop)."""
    image = np.arange(3 * 4 * 5, dtype=np.float32).reshape(3, 4, 5)
    calls: list[tuple[int, ...]] = []

    def fake_denoise_wavelet(data, **kwargs):  # noqa: ANN001
        _ = kwargs
        arr = np.asarray(data, dtype=np.float32)
        calls.append(tuple(arr.shape))
        return arr + 1.0

    monkeypatch.setattr(denoise_model, "denoise_wavelet", fake_denoise_wavelet)
    out = denoise_model.wavelet_denoise_input(image, enabled=True)

    assert calls == [image.shape]
    assert out.dtype == np.float32
    assert np.allclose(out, image + 1.0)
