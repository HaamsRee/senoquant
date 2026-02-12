"""Smoke tests for prediction tab frontend behavior."""

from __future__ import annotations

import numpy as np

from senoquant.tabs.prediction.backend import PredictionBackend
from senoquant.tabs.prediction.frontend import PredictionTab
from tests.conftest import DummyLayer, DummyViewer, Image


class _ImageCaptureViewer(DummyViewer):
    """Viewer stub that records image layers added by prediction runs."""

    def __init__(self, layers: list[DummyLayer] | None = None) -> None:
        super().__init__(layers)
        self.added_images: list[DummyLayer] = []

    def add_image(self, data, name: str, metadata=None, **_kwargs):
        layer = DummyLayer(np.asarray(data), name, metadata=metadata or {})
        self.layers.append(layer)
        self.added_images.append(layer)
        return layer


def test_prediction_tab_instantiates() -> None:
    """Instantiate prediction tab with default backend."""
    viewer = _ImageCaptureViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = PredictionTab(napari_viewer=viewer, backend=PredictionBackend())
    assert hasattr(tab, "_model_combo")
    assert tab._model_combo.currentText() == "demo_model"
    assert not hasattr(tab, "_layer_combo")


def test_prediction_tab_run_pushes_image_layer() -> None:
    """Run prediction model and verify output image layer + metadata."""
    image = Image(np.linspace(0, 1, 16, dtype=np.float32).reshape(4, 4), "img")
    viewer = _ImageCaptureViewer([image])
    tab = PredictionTab(napari_viewer=viewer, backend=PredictionBackend())

    tab._run_prediction()

    assert len(viewer.added_images) == 1
    output_layer = viewer.added_images[0]
    assert output_layer.name == "img_demo_model"
    assert output_layer.metadata.get("task") == "prediction"
    assert output_layer.metadata["run_history"][-1]["runner_name"] == "demo_model"


def test_prediction_demo_model_clips_to_dtype_limits() -> None:
    """Scale output and clip to source dtype limits."""
    image = Image(np.array([[200, 250]], dtype=np.uint8), "img")
    viewer = _ImageCaptureViewer([image])
    tab = PredictionTab(napari_viewer=viewer, backend=PredictionBackend())

    widget = tab._model_widget
    assert widget is not None
    widget.multiplier_spin.setValue(2.0)

    tab._run_prediction()

    output_layer = viewer.added_images[-1]
    assert output_layer.data.dtype == np.uint8
    assert int(output_layer.data.max()) == 255
