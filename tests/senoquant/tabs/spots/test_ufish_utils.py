"""Tests for U-FISH utilities."""

from __future__ import annotations

import numpy as np
from senoquant.tabs.spots.ufish_utils import core as ufish_core

# ruff: noqa: S101, SLF001


class _DummyUFish:
    def __init__(self) -> None:
        self.load_calls: list[tuple[str, ...]] = []
        self.predict_calls: int = 0

    def load_weights(self, path: str | None = None) -> None:
        if path is None:
            self.load_calls.append(())
        else:
            self.load_calls.append((path,))

    def load_weights_from_internet(self) -> None:
        self.load_calls.append(("internet",))

    def predict(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        self.predict_calls += 1
        enhanced = np.asarray(image, dtype=np.float32) + 1.0
        return np.zeros((0,)), enhanced


def _reset_state() -> None:
    ufish_core._UFISH_STATE.model = None
    ufish_core._UFISH_STATE.weights_loaded = False


def test_enhance_image_default_weights(monkeypatch) -> None:
    """Default path should call load_weights once and return enhanced image."""
    _reset_state()
    monkeypatch.setattr(ufish_core, "UFish", _DummyUFish)

    image = np.zeros((4, 4), dtype=np.float32)
    enhanced = ufish_core.enhance_image(image)

    assert enhanced.shape == image.shape
    np.testing.assert_array_equal(enhanced, image + 1.0)

    model = ufish_core._UFISH_STATE.model
    assert isinstance(model, _DummyUFish)
    assert model.load_calls == [()]
    assert model.predict_calls == 1


def test_enhance_image_weights_path(monkeypatch, tmp_path) -> None:
    """Weights path should be respected when provided."""
    _reset_state()
    monkeypatch.setattr(ufish_core, "UFish", _DummyUFish)

    image = np.zeros((2, 2), dtype=np.float32)
    weights_path = tmp_path / "weights"
    config = ufish_core.UFishConfig(weights_path=str(weights_path))
    _ = ufish_core.enhance_image(image, config=config)

    model = ufish_core._UFISH_STATE.model
    assert isinstance(model, _DummyUFish)
    assert model.load_calls == [(str(weights_path),)]


def test_enhance_image_from_internet(monkeypatch) -> None:
    """Internet download path should be used when requested."""
    _reset_state()
    monkeypatch.setattr(ufish_core, "UFish", _DummyUFish)

    image = np.zeros((2, 2), dtype=np.float32)
    config = ufish_core.UFishConfig(load_from_internet=True)
    _ = ufish_core.enhance_image(image, config=config)

    model = ufish_core._UFISH_STATE.model
    assert isinstance(model, _DummyUFish)
    assert model.load_calls == [("internet",)]
