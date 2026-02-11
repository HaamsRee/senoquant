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


def test_wavelet_denoise_input_passes_sigma(monkeypatch) -> None:
    """Forward an explicit sigma value to skimage's denoiser."""
    image = np.arange(12, dtype=np.float32).reshape(3, 4)
    sigma_values: list[float | None] = []

    def fake_denoise_wavelet(data, **kwargs):  # noqa: ANN001
        _ = data
        sigma_values.append(kwargs.get("sigma"))
        return np.asarray(image, dtype=np.float32)

    monkeypatch.setattr(denoise_model, "denoise_wavelet", fake_denoise_wavelet)
    out = denoise_model.wavelet_denoise_input(image, enabled=True, sigma=0.2)

    assert out.dtype == np.float32
    assert sigma_values == [0.2]


def test_bilateral_denoise_input_disabled_returns_float32() -> None:
    """Return float32 data unchanged when bilateral denoising is disabled."""
    image = np.arange(12, dtype=np.float64).reshape(3, 4)
    out = denoise_model.bilateral_denoise_input(image, enabled=False)
    assert out.dtype == np.float32
    assert np.allclose(out, image.astype(np.float32))


def test_bilateral_denoise_input_3d_calls_bilateral_per_slice(monkeypatch) -> None:
    """Apply bilateral denoising per z-slice for 3D stacks."""
    image = np.arange(3 * 4 * 5, dtype=np.float32).reshape(3, 4, 5)
    calls: list[tuple[int, ...]] = []

    def fake_denoise_bilateral(data, **kwargs):  # noqa: ANN001
        _ = kwargs
        arr = np.asarray(data, dtype=np.float32)
        calls.append(tuple(arr.shape))
        return arr + 1.0

    monkeypatch.setattr(denoise_model, "denoise_bilateral", fake_denoise_bilateral)
    out = denoise_model.bilateral_denoise_input(image, enabled=True)

    assert calls == [(4, 5), (4, 5), (4, 5)]
    assert out.dtype == np.float32
    assert np.allclose(out, image + 1.0)
