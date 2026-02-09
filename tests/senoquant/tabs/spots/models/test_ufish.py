"""Tests for the U-FISH local-maxima seeded watershed detector."""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.spots.models.ufish import model as ufish_model


class DummyLayer:
    """Layer stub with data and rgb flag."""

    def __init__(self, data, rgb: bool = False) -> None:
        self.data = data
        self.rgb = rgb


def test_ufish_detector_returns_instances_for_two_peaks(monkeypatch) -> None:
    """Detect two separated spots as two instance labels."""
    image = np.zeros((11, 11), dtype=np.float32)
    image[3, 3] = 0.95
    image[7, 7] = 0.90
    image[3, 2] = 0.70
    image[3, 4] = 0.70
    image[7, 6] = 0.72
    image[7, 8] = 0.72

    monkeypatch.setattr(
        ufish_model,
        "enhance_image",
        lambda arr, config=None: np.asarray(arr, dtype=np.float32),
    )
    monkeypatch.setattr(
        ufish_model,
        "wavelet_denoise_input",
        lambda arr, *, enabled: np.asarray(arr, dtype=np.float32),
    )

    detector = ufish_model.UFishDetector()
    result = detector.run(layer=DummyLayer(image), settings={"threshold": 0.5})
    labels = result["mask"]

    assert labels.shape == image.shape
    assert labels.dtype == np.int32
    assert int(labels.max()) >= 2


def test_ufish_detector_threshold_suppresses_all_spots(monkeypatch) -> None:
    """High thresholds should yield no labels."""
    image = np.zeros((9, 9), dtype=np.float32)
    image[2, 2] = 0.7
    image[6, 6] = 0.8

    monkeypatch.setattr(
        ufish_model,
        "enhance_image",
        lambda arr, config=None: np.asarray(arr, dtype=np.float32),
    )

    detector = ufish_model.UFishDetector()
    result = detector.run(layer=DummyLayer(image), settings={"threshold": 1.0})
    labels = result["mask"]

    assert labels.shape == image.shape
    assert int(labels.max()) == 0


def test_ufish_detector_rejects_rgb() -> None:
    """Reject RGB layer data."""
    detector = ufish_model.UFishDetector()
    with pytest.raises(ValueError):
        detector.run(layer=DummyLayer(np.zeros((5, 5, 3), dtype=np.float32), rgb=True))


def test_ufish_detector_none_layer() -> None:
    """Return empty result when no layer is provided."""
    detector = ufish_model.UFishDetector()
    result = detector.run(layer=None)
    assert result["mask"] is None
    assert result["points"] is None


def test_ufish_detector_calls_enhance(monkeypatch) -> None:
    """Run U-FISH enhancement before local-maxima watershed."""
    image = np.zeros((13, 13), dtype=np.float32)
    image[4, 4] = 0.95
    image[9, 9] = 0.92

    called = {"value": False, "shape": None}

    def fake_enhance(arr: np.ndarray, config=None) -> np.ndarray:
        _ = config
        called["value"] = True
        called["shape"] = tuple(arr.shape)
        return np.asarray(arr, dtype=np.float32)

    monkeypatch.setattr(ufish_model, "enhance_image", fake_enhance)

    detector = ufish_model.UFishDetector()
    result = detector.run(
        layer=DummyLayer(image),
        settings={"threshold": 0.5},
    )
    labels = result["mask"]

    assert called["value"] is True
    assert called["shape"] is not None
    assert called["shape"] == image.shape
    assert labels.shape == image.shape
    assert labels.dtype == np.int32


@pytest.mark.parametrize("legacy_setting", [True, False])
def test_ufish_detector_always_denoises_input(
    monkeypatch,
    legacy_setting: bool,
) -> None:
    """Always run denoising regardless of any legacy denoise setting."""
    image = np.zeros((9, 9), dtype=np.float32)
    image[4, 4] = 1.0
    calls: list[bool] = []

    monkeypatch.setattr(
        ufish_model,
        "enhance_image",
        lambda arr, config=None: np.asarray(arr, dtype=np.float32),
    )

    def fake_wavelet_denoise(array: np.ndarray, *, enabled: bool) -> np.ndarray:
        _ = np.asarray(array, dtype=np.float32)
        calls.append(enabled)
        return np.asarray(array, dtype=np.float32)

    monkeypatch.setattr(ufish_model, "wavelet_denoise_input", fake_wavelet_denoise)

    detector = ufish_model.UFishDetector()
    result = detector.run(
        layer=DummyLayer(image),
        settings={"denoise_enabled": legacy_setting, "threshold": 0.5},
    )

    assert result["mask"].shape == image.shape
    assert calls == [True]
