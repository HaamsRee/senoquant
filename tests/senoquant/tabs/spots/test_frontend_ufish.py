"""Tests for U-FISH integration in spots frontend."""

from __future__ import annotations

import numpy as np

from tests.conftest import DummyViewer, Image
from senoquant.tabs.spots import frontend as spots_frontend

# ruff: noqa: EM101, S101, SLF001, TRY003


class _DummyLayer:
    def __init__(
        self,
        data: np.ndarray,
        *,
        rgb: bool = False,
        name: str = "layer",
    ) -> None:
        self.data = data
        self.rgb = rgb
        self.name = name


def test_ufish_checkbox_default_checked() -> None:
    """Checkbox defaults to enabled for U-FISH."""
    tab = spots_frontend.SpotsTab()

    assert tab._ufish_checkbox is not None
    assert tab._ufish_checkbox.isChecked() is True


def test_prepare_ufish_layer_disabled_returns_original() -> None:
    """Disable checkbox returns original layer."""
    tab = spots_frontend.SpotsTab()
    layer = _DummyLayer(np.zeros((4, 4), dtype=np.float32))

    checkbox = tab._ufish_checkbox
    if checkbox is None:
        msg = "U-FISH checkbox missing."
        raise RuntimeError(msg)
    checkbox.setChecked(False)

    result = tab._prepare_ufish_layer(layer)

    assert result is layer


def test_prepare_ufish_layer_applies_enhancement(monkeypatch: object) -> None:
    """Enabled checkbox applies U-FISH enhancement."""
    tab = spots_frontend.SpotsTab()
    layer = _DummyLayer(np.ones((3, 3), dtype=np.float32), rgb=False, name="spots")

    def fake_enhance(
        image: np.ndarray,
        *,
        config: object | None = None,
    ) -> np.ndarray:
        _ = config
        return np.asarray(image, dtype=np.float32) + 2.0

    monkeypatch.setattr(spots_frontend, "enhance_image", fake_enhance)

    result = tab._prepare_ufish_layer(layer)

    assert isinstance(result, spots_frontend._LayerShim)
    np.testing.assert_array_equal(result.data, layer.data + 2.0)
    assert result.rgb is False
    assert result.name == "spots"


def test_spot_labels_include_task_metadata() -> None:
    """Tag generated spot labels with task metadata."""
    viewer = DummyViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = spots_frontend.SpotsTab(napari_viewer=viewer)
    source = Image(
        np.zeros((4, 4), dtype=np.float32),
        "img",
        metadata={"path": "file.tif"},
    )

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "detector")

    labels_layer = viewer.layers["img_detector_spot_labels"]
    assert labels_layer.metadata.get("task") == "spots"
    assert labels_layer.metadata.get("path") == "file.tif"
