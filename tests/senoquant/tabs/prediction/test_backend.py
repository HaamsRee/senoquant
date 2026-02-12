"""Tests for prediction backend model management and viewer layer output."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from senoquant.tabs.prediction.backend import PredictionBackend
from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel
from tests.conftest import DummyLayer, Image


class _SettingsWidget:
    """Simple settings widget stub used by backend tests."""

    def __init__(self, scale: float) -> None:
        self.scale = float(scale)


class _Viewer:
    """Viewer stub that captures image layers added by the backend."""

    def __init__(self, layers: list[DummyLayer]) -> None:
        self.layers = layers
        self.added_layers: list[DummyLayer] = []

    def add_image(self, data, name: str, metadata=None, **_kwargs):
        layer = DummyLayer(data=np.asarray(data), name=name, metadata=metadata or {})
        self.added_layers.append(layer)
        return layer


def _write_prediction_model(tmp_path: Path, name: str, order: int = 1) -> None:
    model_dir = tmp_path / name
    model_dir.mkdir(parents=True)
    (model_dir / "model.py").write_text(
        "import numpy as np\n"
        "from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel\n"
        "\n"
        "class CustomPredictionModel(SenoQuantPredictionModel):\n"
        "    def __init__(self, models_root=None):\n"
        f"        super().__init__('{name}', models_root=models_root)\n"
        "\n"
        "    def display_order(self):\n"
        f"        return {float(order)}\n"
        "\n"
        "    def collect_widget_settings(self, settings_widget=None):\n"
        "        scale = 1.0\n"
        "        if settings_widget is not None:\n"
        "            scale = float(getattr(settings_widget, 'scale', 1.0))\n"
        "        return {'scale': scale}\n"
        "\n"
        "    def run(self, **kwargs):\n"
        "        viewer = kwargs.get('viewer')\n"
        "        settings = kwargs.get('settings', {}) or {}\n"
        "        scale = float(settings.get('scale', 1.0))\n"
        "        layer = next(iter(viewer.layers), None)\n"
        "        if layer is None:\n"
        "            return {'layers': []}\n"
        "        data = np.asarray(layer.data, dtype=np.float32) * scale\n"
        "        return {\n"
        "            'layers': [\n"
        "                {\n"
        "                    'data': data,\n"
        "                    'type': 'image',\n"
        "                    'name': 'scaled_score'\n"
        "                }\n"
        "            ]\n"
        "        }\n",
        encoding="utf-8",
    )


def test_list_model_names_orders_by_display_order(tmp_path: Path) -> None:
    """Sort prediction models by explicit order, then by model name."""
    _write_prediction_model(tmp_path, "model_b", order=2)
    _write_prediction_model(tmp_path, "model_a", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    assert backend.list_model_names() == ["model_a", "model_b"]


def test_get_model_loads_prediction_subclass(tmp_path: Path) -> None:
    """Load concrete prediction model classes from model.py."""
    _write_prediction_model(tmp_path, "model_custom", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    model = backend.get_model("model_custom")
    assert isinstance(model, SenoQuantPredictionModel)
    assert model.name == "model_custom"


def test_run_model_and_push_layers_to_viewer(tmp_path: Path) -> None:
    """Run prediction model and push output layer with run metadata."""
    _write_prediction_model(tmp_path, "model_score", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    source_image = Image(
        data=np.ones((3, 3), dtype=np.float32),
        name="input",
        metadata={"sample_id": "s1"},
    )
    viewer = _Viewer([source_image])

    result = backend.run_model(
        model_name="model_score",
        viewer=viewer,
        settings_widget=_SettingsWidget(scale=2.5),
    )

    assert result["settings"] == {"scale": 2.5}

    added_layers = backend.push_layers_to_viewer(
        viewer=viewer,
        source_layer=None,
        model_name="model_score",
        result=result,
    )

    assert len(added_layers) == 1
    added = added_layers[0]
    assert np.allclose(added.data, 2.5)
    assert added.name == "scaled_score"
    assert added.metadata.get("task") == "prediction"
    assert added.metadata["run_history"][-1]["runner_name"] == "model_score"
    assert added.metadata["run_history"][-1]["settings"] == {"scale": 2.5}
