# Models & Detectors

SenoQuant discovers segmentation models and spot detectors at runtime by
scanning folders under the respective `models` directories.

## Segmentation models

Location:

- `src/senoquant/tabs/segmentation/models/<model_name>`

Discovery rules:

- The folder name becomes the model name.
- If `model.py` exists, the first subclass of
  `SenoQuantSegmentationModel` is instantiated.
- If `model.py` is missing, the base wrapper is used (metadata-only).

Metadata:

- `details.json` defines the UI settings and task support.
- The Segmentation tab uses `details.json` to build the settings form and
  to filter models by task.

Example `details.json` structure:

```json
{
  "name": "example_model",
  "description": "Short description",
  "version": "0.1.0",
  "tasks": {
    "nuclear": {"supported": true},
    "cytoplasmic": {
      "supported": true,
      "input_modes": ["cytoplasmic", "nuclear+cytoplasmic"],
      "nuclear_channel_optional": false
    }
  },
  "settings": [
    {
      "key": "object_diameter_px",
      "label": "Object diameter (px)",
      "type": "float",
      "decimals": 1,
      "min": 1.0,
      "max": 500.0,
      "default": 30.0
    }
  ]
}
```

UI settings behavior:

- `type` selects the widget type (`int`, `float`, or `bool`).
- `enabled_by` and `disabled_by` toggle widgets based on other settings.

## Spot detectors

Location:

- `src/senoquant/tabs/spots/models/<detector_name>`

Discovery rules mirror segmentation:

- The folder name becomes the detector name.
- `model.py` is optional but recommended for custom logic.
- `details.json` controls settings shown in the Spots tab.

Detector settings schema matches segmentation settings (minus task info).

## StarDist ONNX conversion utilities

The repository ships a StarDist ONNX conversion helper under
`src/senoquant/tabs/segmentation/stardist_onnx_utils`. The README documents
the recommended environment and commands. Example usage:

```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 2 --model 2D_versatile_fluo --output ./onnx_models
```
