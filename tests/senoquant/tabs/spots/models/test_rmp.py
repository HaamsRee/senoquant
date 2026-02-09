"""Tests for the RMP spot detector helpers.

Notes
-----
Exercises normalization, padding, and marker/segmentation helpers.
"""

from __future__ import annotations

import numpy as np
import pytest

from senoquant.tabs.spots.models.rmp import model as rmp


class DummyLayer:
    """Layer stub with data and rgb flag."""

    def __init__(self, data, rgb: bool = False) -> None:
        self.data = data
        self.rgb = rgb


def test_normalize_image_constant() -> None:
    """Normalize constant image to zeros.

    Returns
    -------
    None
    """
    data = np.ones((4, 4), dtype=np.float32)
    normalized = rmp._normalize_image(data)
    assert np.allclose(normalized, 0.0)


def test_pad_tensor_for_rotation_grows_canvas() -> None:
    """Pad tensor so rotations keep content."""
    data = np.zeros((4, 6), dtype=np.float32)
    device = rmp._torch_device()
    tensor = rmp._to_image_tensor(data, device=device)
    padded, (pad_y, pad_x) = rmp._pad_tensor_for_rotation(tensor)
    assert int(padded.shape[-2]) >= data.shape[0]
    assert int(padded.shape[-1]) >= data.shape[1]
    assert pad_y >= 0 and pad_x >= 0


def test_markers_from_local_maxima_empty() -> None:
    """Return empty markers when no local maxima cross threshold."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = rmp._markers_from_local_maxima(enhanced, threshold=0.5)
    assert markers.shape == enhanced.shape
    assert markers.max() == 0


def test_segment_from_markers_empty_foreground() -> None:
    """Return zeros when threshold removes all foreground."""
    enhanced = np.zeros((4, 4), dtype=np.float32)
    markers = np.zeros((4, 4), dtype=np.int32)
    labels = rmp._segment_from_markers(enhanced, markers, threshold=0.5)
    assert labels.shape == enhanced.shape
    assert labels.max() == 0


@pytest.mark.parametrize("legacy_setting", [True, False])
def test_rmp_detector_denoises_input_and_top_hat(
    monkeypatch,
    legacy_setting: bool,
) -> None:
    """Always denoise input and top-hat, even when legacy setting is present."""
    image = np.zeros((9, 9), dtype=np.float32)
    image[4, 4] = 1.0
    calls: list[tuple[np.ndarray, bool]] = []

    monkeypatch.setattr(rmp, "layer_data_asarray", lambda layer: np.asarray(layer.data))
    monkeypatch.setattr(
        rmp,
        "_normalize_image",
        lambda array: np.asarray(array, dtype=np.float32),
    )

    def fake_wavelet_denoise(array: np.ndarray, *, enabled: bool) -> np.ndarray:
        arr = np.asarray(array, dtype=np.float32)
        calls.append((arr.copy(), enabled))
        if enabled:
            return arr + 10.0
        return arr

    monkeypatch.setattr(rmp, "wavelet_denoise_input", fake_wavelet_denoise)
    monkeypatch.setattr(rmp, "_dask_available", lambda: False)
    monkeypatch.setattr(rmp, "_distributed_available", lambda: False)
    monkeypatch.setattr(
        rmp,
        "_compute_top_hat_nd",
        lambda array, config, **_: np.asarray(array, dtype=np.float32) + 5.0,
    )
    captured_top_hat: dict[str, np.ndarray] = {}

    def fake_postprocess(top_hat: np.ndarray, config) -> tuple[np.ndarray, np.ndarray]:
        _ = config
        arr = np.asarray(top_hat, dtype=np.float32)
        captured_top_hat["value"] = arr
        return np.zeros_like(arr, dtype=np.int32), arr

    monkeypatch.setattr(rmp, "_postprocess_top_hat", fake_postprocess)

    detector = rmp.RMPDetector()
    result = detector.run(
        layer=DummyLayer(image),
        settings={"enable_denoising": legacy_setting},
    )

    assert result["mask"].shape == image.shape
    assert len(calls) == 2
    assert calls[0][1] is True
    assert calls[1][1] is True
    expected_top_hat_input = calls[0][0] + 10.0 + 5.0
    assert np.allclose(calls[1][0], expected_top_hat_input)
    expected_postprocess_input = calls[1][0] + 10.0
    assert np.allclose(captured_top_hat["value"], expected_postprocess_input)
