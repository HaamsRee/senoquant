# Prediction models

This guide covers the Prediction tab framework for running computer-vision
models that predict senescence-associated features from napari images.

Prediction code lives in:

- `src/senoquant/tabs/prediction/frontend.py`
- `src/senoquant/tabs/prediction/backend.py`
- `src/senoquant/tabs/prediction/models/base.py`
- `src/senoquant/tabs/prediction/models/`

## Tab UI contract

The tab-level UI is intentionally minimal and fixed:

- **Select model** dropdown at the top.
- **Model interface** group box that hosts model-defined Qt controls.
- **Run** button outside the model interface box.

The base tab does not define a generic image/layer selector. Each model owns its
own input controls in its widget.

## Discovery and loading

Model discovery is folder-based under:

- `src/senoquant/tabs/prediction/models/<model_name>/`

`PredictionBackend.list_model_names()` scans these folders and sorts by:

1. `model.display_order()` (lower first).
2. Model name.

Model class loading behavior (`PredictionBackend.get_model()`):

- Loads `<model_name>/model.py` dynamically.
- Uses the first subclass of `SenoQuantPredictionModel` found.
- Falls back to `SenoQuantPredictionModel` when no concrete class is found.

Unlike segmentation/spots, prediction models do not require `details.json`.

## Base class contract

Subclass `SenoQuantPredictionModel` from:

- `src/senoquant/tabs/prediction/models/base.py`

Key methods:

- `display_order(self) -> float | None`: optional selector ordering.
- `build_widget(self, parent=None, viewer=None) -> QWidget | None`: create model UI.
- `collect_widget_settings(self, settings_widget=None) -> dict[str, object]`: serialize UI state.
- `run(self, **kwargs) -> dict`: execute model and return output layer specs.

Run payload currently includes:

- `viewer`: napari viewer instance.
- `settings`: serialized settings from `collect_widget_settings()`.

## Output contract and normalization

Prediction output is handled by `PredictionBackend.run_model()` and
`PredictionBackend.push_layers_to_viewer()`.

A model can return:

- `{"layers": [...]}` (preferred), optionally with `"settings"`.
- A raw sequence of layer specs (wrapped as `layers` by the backend).

Each layer spec may be:

- Mapping form:
  - required: `data`
  - optional: `type` (`image`, `labels`, `points`, ...), `kwargs`, and any extra napari kwargs
- Tuple/list form:
  - `(data,)`
  - `(data, kwargs)`
  - `(data, kwargs, layer_type)`

If no layer name is supplied, backend assigns:

- `<source_or_model>_<model_name>_prediction_<index>`

For each added layer, backend appends run metadata via
`senoquant.utils.append_run_metadata(...)`:

- `task="prediction"`
- `runner_type="prediction_model"`
- `runner_name=<model_name>`
- serialized `settings`

## Demo model reference

Current placeholder model:

- `src/senoquant/tabs/prediction/models/demo_model/model.py`

It demonstrates:

- building a custom Qt widget
- selecting a napari image layer
- collecting widget settings
- running simple inference logic
- returning an image layer payload

## Add a new prediction model

1. Create folder:
   `src/senoquant/tabs/prediction/models/my_model/`
2. Add `model.py` with a `SenoQuantPredictionModel` subclass.
3. Implement `build_widget()`, `collect_widget_settings()`, and `run()`.
4. Restart napari and verify it appears in **Select model**.

Minimal template:

```python
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel


class MyModelWidget(QWidget):
    def __init__(self, viewer, parent=None) -> None:
        super().__init__(parent)
        self._viewer = viewer
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Configure my model here"))
        self.setLayout(layout)

    def values(self) -> dict[str, object]:
        return {"example": 1}


class MyModel(SenoQuantPredictionModel):
    def __init__(self, models_root=None) -> None:
        super().__init__("my_model", models_root=models_root)

    def build_widget(self, parent=None, viewer=None):
        return MyModelWidget(viewer=viewer, parent=parent)

    def collect_widget_settings(self, settings_widget=None) -> dict[str, object]:
        if settings_widget is None:
            return {}
        return settings_widget.values()

    def run(self, **kwargs) -> dict:
        viewer = kwargs.get("viewer")
        settings = kwargs.get("settings", {})
        # Compute prediction output from viewer + settings.
        return {
            "layers": [
                {
                    "data": ...,  # numpy array
                    "type": "image",
                    "name": "my_prediction_map",
                }
            ]
        }
```

## Test coverage

Prediction tests live in:

- `tests/senoquant/tabs/prediction/test_frontend.py`
- `tests/senoquant/tabs/prediction/test_backend.py`

When you change prediction behavior, update both frontend and backend coverage
as needed.
