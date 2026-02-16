# Models, detectors, and prediction runners

This guide is the source-of-truth for adding:

- Segmentation models.
- Spot detectors.
- Prediction models.

Discovery is folder-based and dynamic across all three systems, but metadata
rules differ:

- Segmentation/Spots read UI schemas from `details.json`.
- Prediction models define UI directly in Qt code and do not require
  `details.json`.

## How discovery works

### Segmentation models

Folder location:

`src/senoquant/tabs/segmentation/models/<model_name>/`

Discovery behavior:

- `SegmentationBackend.list_model_names(task=...)` scans subfolders.
- A model is shown for a task only if `details.json` has
  `tasks.<task>.supported = true`.
- Runtime class loading looks for the first subclass of
  `SenoQuantSegmentationModel` in `model.py`.
- If `model.py` is missing, the base class is used, but `run()` is not
  implemented, so the model is not runnable.

### Spot detectors

Folder location:

`src/senoquant/tabs/spots/models/<detector_name>/`

Discovery behavior:

- `SpotsBackend.list_detector_names()` scans subfolders.
- Runtime class loading looks for the first subclass of
  `SenoQuantSpotDetector` in `model.py`.
- If `model.py` is missing, the base class is used, but `run()` is not
  implemented, so the detector is not runnable.

### Prediction models

Folder location:

`src/senoquant/tabs/prediction/models/<model_name>/`

Discovery behavior:

- `PredictionBackend.list_model_names()` scans subfolders.
- Runtime class loading looks for the first subclass of
  `SenoQuantPredictionModel` in `model.py`.
- `display_order()` controls dropdown ordering (lower first).
- If `model.py` is missing, the base class is used, but `run()` is not
  implemented, so the model is not runnable.

## Metadata schema (`details.json`) for segmentation and spots

Both segmentation and spots use a `settings` list to auto-build the UI.
Manifest validation is enforced at load time via:

- `src/senoquant/utils/model_details.schema.json`
- `src/senoquant/utils/model_details_schema.py`
- `SenoQuantSegmentationModel.load_details()` (requires `tasks`)
- `SenoQuantSpotDetector.load_details()` (does not require `tasks`)

If validation fails, model/detector loading raises a `ValueError` with the
`details.json` path and validation message.

### Required top-level keys (all models/detectors)

- `name` (string)
- `description` (string)
- `version` (string)
- `settings` (array)

### Segmentation-only requirement

- `tasks` object must be present and include both:
  - `tasks.nuclear`
  - `tasks.cytoplasmic`

Supported setting types:

- Use `float`.
- Use `int`.
- Use `bool`.

Supported dependency keys:

- `enabled_by`: setting key of a controlling checkbox.
- `disabled_by`: setting key of a controlling checkbox.

Notes:

- In current UI code, `enabled_by` and `disabled_by` are treated as a
  single key string.
- `order` controls dropdown sorting (lower comes first).
- For `float` and `int` settings, `min`, `max`, and `default` are required.
- For `bool` settings, `default` is required.

### Segmentation-specific fields

Example:

```json
{
  "name": "my_model",
  "description": "Custom segmentation model.",
  "version": "0.1.0",
  "order": 30,
  "tasks": {
    "nuclear": { "supported": true },
    "cytoplasmic": {
      "supported": true,
      "input_modes": ["cytoplasmic", "nuclear+cytoplasmic", "nuclear"],
      "nuclear_channel_optional": false
    }
  },
  "settings": []
}
```

`input_modes` behavior:

- `["cytoplasmic"]`: cytoplasmic image only.
- Includes `nuclear+cytoplasmic`: uses both cytoplasmic and nuclear inputs.
- `["nuclear"]`: nuclear-only cytoplasmic model (no cytoplasmic image).

### Spots-specific fields

Example:

```json
{
  "name": "my_detector",
  "description": "Custom spot detector.",
  "version": "0.1.0",
  "order": 30,
  "settings": []
}
```

## Prediction model conventions (no `details.json`)

Prediction models are code-driven. Required file:

- `src/senoquant/tabs/prediction/models/<model_name>/model.py`

The tab-level controls are fixed in
`src/senoquant/tabs/prediction/frontend.py`:

- `Select model` dropdown.
- `Model interface` box (model-defined widget).
- `Run` button outside the box.

Each model class should:

- Subclass `SenoQuantPredictionModel`.
- Optionally implement `display_order()` for dropdown sorting.
- Implement `build_widget(parent, viewer)` for model-specific controls.
- Implement `collect_widget_settings(settings_widget)` for serializable settings.
- Implement `run(viewer=..., settings=...)` returning prediction layer specs.

Prediction backend accepts output layer specs as dicts or tuple-like payloads;
see `PredictionBackend._normalize_layer_spec(...)` in
`src/senoquant/tabs/prediction/backend.py`.

## Add a new segmentation model

1. Create the folder:
   `src/senoquant/tabs/segmentation/models/my_model/`.
2. Add `details.json` with `tasks` and `settings`.
3. Add `model.py` with a subclass of `SenoQuantSegmentationModel`.
4. Implement `run(self, **kwargs)` and return `{"masks": <label_array>}`.
5. Restart napari and verify the model appears in the correct task dropdown.

Minimal template:

```python
from pathlib import Path
from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
from senoquant.utils import layer_data_asarray


class MySegmentationModel(SenoQuantSegmentationModel):
    def __init__(self, models_root: Path | None = None) -> None:
        super().__init__("my_model", models_root=models_root)

    def run(self, **kwargs) -> dict:
        task = kwargs.get("task")
        settings = kwargs.get("settings", {}) or {}

        if task == "nuclear":
            layer = kwargs.get("layer")
            image = layer_data_asarray(layer)
        elif task == "cytoplasmic":
            # Segmentation tab passes `cytoplasmic_layer`.
            # Batch currently passes `layer` for the same input.
            cyto_layer = kwargs.get("cytoplasmic_layer") or kwargs.get("layer")
            nuclear_layer = kwargs.get("nuclear_layer")
            # pick the inputs your mode requires
            image = layer_data_asarray(cyto_layer or nuclear_layer)
        else:
            raise ValueError(f"Unsupported task: {task}")

        masks = my_segmentation_function(image, settings)
        return {"masks": masks}
```

Important runtime contracts:

- Nuclear runs pass `task="nuclear"` and `layer=<Image>`.
- Cytoplasmic runs pass `task="cytoplasmic"` and:
  - Segmentation tab: `cytoplasmic_layer`, optional `nuclear_layer`.
  - Batch path: `layer`, optional `nuclear_layer`.
  - nuclear-only models (`input_modes == ["nuclear"]`): `nuclear_layer`.

## Add a new spots detector

1. Create the folder:
   `src/senoquant/tabs/spots/models/my_detector/`.
2. Add `details.json`.
3. Add `model.py` with a subclass of `SenoQuantSpotDetector`.
4. Implement `run(self, **kwargs)` and return `{"mask": <label_array>}`.
5. Restart napari and verify detector appears in Spots dropdown.

Minimal template:

```python
from pathlib import Path
from senoquant.tabs.spots.models.base import SenoQuantSpotDetector
from senoquant.utils import layer_data_asarray


class MyDetector(SenoQuantSpotDetector):
    def __init__(self, models_root: Path | None = None) -> None:
        super().__init__("my_detector", models_root=models_root)

    def run(self, **kwargs) -> dict:
        layer = kwargs.get("layer")
        settings = kwargs.get("settings", {}) or {}
        image = layer_data_asarray(layer)
        mask = my_spot_detector(image, settings)
        return {"mask": mask}
```

Important runtime contracts:

- Detector runs receive `layer` and `settings`.
- Output layer naming and metadata are handled in `SpotsTab`, not in the
  detector.
- Both Spots tab and Batch apply optional post-detection filtering through
  `_filter_labels_by_size(...)` (`src/senoquant/tabs/spots/frontend.py`).
- `min_size` / `max_size` values are treated as diameter thresholds (pixels):
  2D uses effective area (`pi * (d/2)^2`), 3D uses effective volume
  (`(4/3) * pi * (d/2)^3`).

## Add a new prediction model

1. Create the folder:
   `src/senoquant/tabs/prediction/models/my_model/`.
2. Add `model.py` with a subclass of `SenoQuantPredictionModel`.
3. Implement `build_widget()`, `collect_widget_settings()`, and `run()`.
4. Return output as layer specs under a `layers` list.
5. Restart napari and verify the model appears in **Select model**.

Minimal template:

```python
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget
from senoquant.tabs.prediction.models.base import SenoQuantPredictionModel


class MyPredictionWidget(QWidget):
    def __init__(self, viewer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._viewer = viewer
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Configure my prediction model"))
        self.setLayout(layout)

    def values(self) -> dict[str, object]:
        return {"scale": 1.0}


class MyPredictionModel(SenoQuantPredictionModel):
    def __init__(self, models_root=None) -> None:
        super().__init__("my_model", models_root=models_root)

    def build_widget(self, parent=None, viewer=None):
        return MyPredictionWidget(viewer=viewer, parent=parent)

    def collect_widget_settings(self, settings_widget=None) -> dict[str, object]:
        if settings_widget is None:
            return {}
        return settings_widget.values()

    def run(self, **kwargs) -> dict:
        settings = kwargs.get("settings", {})
        return {
            "layers": [
                {
                    "data": ...,  # numpy array
                    "type": "image",
                    "name": "my_prediction_output",
                }
            ],
            "settings": settings,
        }
```

## Quick validation checklist

- Folder name, class constructor name, and `super("<name>")` all match.
- Segmentation/Spots: `details.json` passes `model_details.schema.json` validation.
- Segmentation manifests include both `tasks.nuclear` and `tasks.cytoplasmic`.
- `run()` returns expected keys:
  - Segmentation: `masks`.
  - Spots: `mask`.
  - Prediction: `layers` (or a sequence normalized by backend).
- Settings keys in code match `details.json` keys (segmentation/spots only).
- New model/detector/prediction runner appears in UI and can run on a sample image.

## StarDist ONNX notes

The StarDist conversion utilities and compiled extension still live under:

- `src/senoquant/tabs/segmentation/stardist_onnx_utils/`.
- `stardist_ext/`.

For conversion workflow details, see `docs/developer/stardist-onnx.md`.
For packaging details, see `docs/developer/packaging.md`.
