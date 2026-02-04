# Models and detectors

This guide is the source-of-truth for adding new segmentation models and
spot detectors.

Model and detector discovery are folder-based and dynamic. The UI reads
metadata from `details.json`, and runtime code is loaded from `model.py`.

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

## Metadata schema (`details.json`)

Both segmentation and spots use a `settings` list to auto-build the UI.

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
- Batch also applies optional min/max spot size filtering after detector run.

## Quick validation checklist

- Folder name, class constructor name, and `super("<name>")` all match.
- `details.json` is valid JSON and contains task support (segmentation).
- `run()` returns expected keys (`masks` for segmentation, `mask` for spots).
- Settings keys in code match settings keys in `details.json`.
- New model/detector appears in UI and can run on a sample image.

## StarDist ONNX notes

The StarDist conversion utilities and compiled extension still live under:

- `src/senoquant/tabs/segmentation/stardist_onnx_utils/`.
- `stardist_ext/`.

For packaging details, see `docs/developer/packaging.md`.
