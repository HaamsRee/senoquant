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


def test_run_model_with_none_result(tmp_path: Path) -> None:
    """Test run_model handles None result from model."""
    _write_prediction_model(tmp_path, "model_none", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    source_image = Image(
        data=np.ones((3, 3), dtype=np.float32),
        name="input",
        metadata={},
    )
    viewer = _Viewer([source_image])

    # Create a model that returns None
    model = backend.get_model("model_none")
    original_run = model.run

    def run_none(**kwargs):
        return None

    model.run = run_none

    result = backend.run_model(
        model_name="model_none",
        viewer=viewer,
        settings_widget=None,
    )

    assert result["layers"] == []
    # Settings come from collect_widget_settings even when run returns None
    assert result["settings"] == {"scale": 1.0}


def test_run_model_with_sequence_result(tmp_path: Path) -> None:
    """Test run_model handles sequence result from model."""
    _write_prediction_model(tmp_path, "model_seq", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    source_image = Image(
        data=np.ones((3, 3), dtype=np.float32),
        name="input",
        metadata={},
    )
    viewer = _Viewer([source_image])

    # Create a model that returns a sequence
    model = backend.get_model("model_seq")
    original_run = model.run

    def run_sequence(**kwargs):
        return [{"data": np.ones((3, 3)), "type": "image", "name": "out1"}]

    model.run = run_sequence

    result = backend.run_model(
        model_name="model_seq",
        viewer=viewer,
        settings_widget=None,
    )

    assert len(result["layers"]) == 1
    assert result["layers"][0]["name"] == "out1"


def test_push_layers_with_no_viewer() -> None:
    """Test push_layers_to_viewer handles None viewer."""
    backend = PredictionBackend()
    result = {"layers": [{"data": np.ones((3, 3)), "type": "image", "name": "test"}]}

    added = backend.push_layers_to_viewer(
        viewer=None,
        model_name="test_model",
        result=result,
    )
    assert added == []


def test_push_layers_with_invalid_result() -> None:
    """Test push_layers_to_viewer handles invalid result."""
    backend = PredictionBackend()

    added = backend.push_layers_to_viewer(
        viewer=_Viewer([]),
        model_name="test_model",
        result="not a dict",
    )
    assert added == []


def test_push_layers_with_empty_layers() -> None:
    """Test push_layers_to_viewer handles empty layers."""
    backend = PredictionBackend()
    result = {"layers": []}

    added = backend.push_layers_to_viewer(
        viewer=_Viewer([]),
        model_name="test_model",
        result=result,
    )
    assert added == []


def test_run_model_raises_on_invalid_result_type(tmp_path: Path) -> None:
    """Test run_model raises ValueError for invalid result type."""
    _write_prediction_model(tmp_path, "model_invalid", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    source_image = Image(
        data=np.ones((3, 3), dtype=np.float32),
        name="input",
        metadata={},
    )
    viewer = _Viewer([source_image])

    # Create a model that returns an invalid type (int)
    model = backend.get_model("model_invalid")

    def run_invalid(**kwargs):
        return 42  # Invalid - should be dict or sequence

    model.run = run_invalid

    try:
        result = backend.run_model(
            model_name="model_invalid",
            viewer=viewer,
            settings_widget=None,
        )
        # Should have raised ValueError
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "must return a dict or a sequence" in str(e)


def test_run_model_raises_on_invalid_layers_type(tmp_path: Path) -> None:
    """Test run_model raises ValueError for invalid layers type."""
    _write_prediction_model(tmp_path, "model_layers_invalid", order=1)

    backend = PredictionBackend(models_root=tmp_path)
    source_image = Image(
        data=np.ones((3, 3), dtype=np.float32),
        name="input",
        metadata={},
    )
    viewer = _Viewer([source_image])

    # Create a model that returns a dict with invalid layers type
    model = backend.get_model("model_layers_invalid")

    def run_invalid_layers(**kwargs):
        return {"layers": "not a sequence"}  # Invalid - layers should be sequence

    model.run = run_invalid_layers

    try:
        result = backend.run_model(
            model_name="model_layers_invalid",
            viewer=viewer,
            settings_widget=None,
        )
        # Should have raised ValueError
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "layers" in str(e) and "sequence" in str(e)


def test_prediction_backend_load_model_class_not_exists(tmp_path: Path) -> None:
    """Test _load_model_class returns None when model.py doesn't exist."""
    backend = PredictionBackend(models_root=tmp_path)
    result = backend._load_model_class("nonexistent_model_xyz")
    assert result is None


def test_prediction_backend_list_model_names_empty_root(tmp_path: Path) -> None:
    """Test list_model_names with non-existent root."""
    non_existent = tmp_path / "nonexistent"
    backend = PredictionBackend(models_root=non_existent)
    names = backend.list_model_names()
    assert names == []


def test_prediction_backend_get_model_without_model_py(tmp_path: Path) -> None:
    """Test get_model creates default model when model.py doesn't exist."""
    # Create a directory without model.py
    model_dir = tmp_path / "model_no_py"
    model_dir.mkdir()

    backend = PredictionBackend(models_root=tmp_path)
    model = backend.get_model("model_no_py")

    # Should return a base SenoQuantPredictionModel
    assert isinstance(model, SenoQuantPredictionModel)
    assert model.name == "model_no_py"
