# Models & Detectors

SenoQuant discovers segmentation models and spot detectors at runtime by
scanning folders under the respective `models` directories.

## Segmentation Models

### Discovery Location

`src/senoquant/tabs/segmentation/models/<model_name>/`

### Discovery Rules

- The folder name becomes the model identifier
- `details.json` is required (defines metadata, settings, and task support)
- `model.py` is optional but recommended for custom implementations
  - If present, the first subclass of `SenoQuantSegmentationModel` is instantiated
  - If absent, the base wrapper is used (metadata-only)

### Metadata Structure

`details.json` defines UI settings, task support, and display ordering:

```json
{
  "name": "model_name",
  "description": "Model description for UI tooltips",
  "version": "0.1.0",
  "order": 1,
  "tasks": {
    "nuclear": {
      "supported": true
    },
    "cytoplasmic": {
      "supported": true,
      "input_modes": ["cytoplasmic", "nuclear+cytoplasmic", "nuclear"],
      "nuclear_channel_optional": false
    }
  },
  "settings": [
    {
      "key": "param_name",
      "label": "Parameter Label",
      "type": "float",
      "decimals": 2,
      "min": 0.0,
      "max": 1.0,
      "default": 0.5,
      "enabled_by": "other_setting",
      "disabled_by": "another_setting"
    }
  ]
}
```

### Current Models

| Model | Type | Dimensionality | Implementation |
| --- | --- | --- | --- |
| `default_2d` | Nuclear | 2D | StarDist ONNX |
| `default_3d` | Nuclear | 3D | StarDist ONNX |
| `cpsam` | Nuclear + Cytoplasmic | 2D/3D | Cellpose SAM |
| `nuclear_dilation` | Cytoplasmic | Any | Morphological dilation |
| `perinuclear_rings` | Cytoplasmic | Any | Morphological erosion/dilation |

### Input Modes (Cytoplasmic Models)

- `"cytoplasmic"` - Requires cytoplasm image only
- `"nuclear+cytoplasmic"` - Requires both cytoplasm and nuclear images
- `"nuclear"` - Requires nuclear mask only (no image input)

### Settings Schema

**Supported types:**
- `"float"` - Floating point number with configurable precision
- `"int"` - Integer number
- `"bool"` - Boolean checkbox

**Optional fields:**
- `enabled_by` (str or list): Enable this setting when another setting is true
- `disabled_by` (str or list): Disable this setting when another setting is true
- `order` (int): Display order in UI (lower = earlier)

## Spot Detectors

### Discovery Location

`src/senoquant/tabs/spots/models/<detector_name>/`

### Discovery Rules

Same pattern as segmentation models:
- Folder name becomes detector identifier
- `details.json` is required
- `model.py` is optional (implements `SenoQuantSpotDetector` subclass)

### Metadata Structure

```json
{
  "name": "detector_name",
  "description": "Detector description",
  "version": "0.1.0",
  "order": 1,
  "settings": [
    {
      "key": "threshold",
      "label": "Detection Threshold",
      "type": "float",
      "decimals": 2,
      "min": 0.0,
      "max": 10.0,
      "default": 1.0
    }
  ]
}
```

### Current Detectors

| Detector | Algorithm | Best For |
| --- | --- | --- |
| `udwt` | Undecimated B3-spline wavelet | Multi-scale spot detection |
| `rmp` | Rotational morphological processing | Spot detection with rotational analysis |

### Settings Schema

Same as segmentation models but without task-specific fields:
- Supports `"int"`, `"float"`, `"bool"` types
- Supports `enabled_by` and `disabled_by` conditional logic
- Uses `order` field for sorting

## Implementation Guide

### Creating a Segmentation Model

1. **Create folder structure:**
   ```
   src/senoquant/tabs/segmentation/models/my_model/
     details.json
     model.py  (optional)
     onnx_models/  (optional, for ONNX models)
   ```

2. **Define details.json:**
   ```json
   {
     "name": "my_model",
     "description": "My custom segmentation model",
     "version": "0.1.0",
     "order": 10,
     "tasks": {
       "nuclear": {"supported": true},
       "cytoplasmic": {"supported": false}
     },
     "settings": [
       {
         "key": "threshold",
         "label": "Threshold",
         "type": "float",
         "decimals": 2,
         "min": 0.0,
         "max": 1.0,
         "default": 0.5
       }
     ]
   }
   ```

3. **Implement model.py (optional):**
   ```python
   from pathlib import Path
   from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel
   
   class MyModel(SenoQuantSegmentationModel):
       def __init__(self, models_root: Path | None = None):
           super().__init__("my_model", models_root=models_root)
       
       def run(self, **kwargs):
           task = kwargs.get("task")
           layer = kwargs.get("layer")
           settings = kwargs.get("settings", {})
           
           # Your segmentation logic here
           image = layer.data
           masks = my_segmentation_function(image, settings)
           
           return {"masks": masks}
   ```

### Creating a Spot Detector

1. **Create folder structure:**
   ```
   src/senoquant/tabs/spots/models/my_detector/
     details.json
     model.py  (optional)
   ```

2. **Define details.json:**
   ```json
   {
     "name": "my_detector",
     "description": "My custom spot detector",
     "version": "0.1.0",
     "order": 10,
     "settings": [
       {
         "key": "sensitivity",
         "label": "Sensitivity",
         "type": "float",
         "decimals": 1,
         "min": 0.0,
         "max": 100.0,
         "default": 50.0
       }
     ]
   }
   ```

3. **Implement model.py (optional):**
   ```python
   from pathlib import Path
   from senoquant.tabs.spots.models.base import SenoQuantSpotDetector
   
   class MyDetector(SenoQuantSpotDetector):
       def __init__(self, models_root: Path | None = None):
           super().__init__("my_detector", models_root=models_root)
       
       def run(self, **kwargs):
           layer = kwargs.get("layer")
           settings = kwargs.get("settings", {})
           
           # Your detection logic here
           image = layer.data
           mask = my_detection_function(image, settings)
           
           return {"mask": mask}
   ```

## StarDist ONNX Conversion

### Overview

SenoQuant includes utilities for converting TensorFlow StarDist models to ONNX format for faster CPU inference.

### Location

`src/senoquant/tabs/segmentation/stardist_onnx_utils/`

### Requirements

- Python 3.11
- TensorFlow 2.x
- tf2onnx
- protobuf >=6.33.4 (must be installed AFTER TensorFlow)

### Environment Setup

```bash
conda create -n stardist-convert python=3.11
conda activate stardist-convert
pip install uv
uv pip install tensorflow tf2onnx
uv pip install --upgrade "protobuf>=6.33.4"  # Force after TF
uv pip install -e .
```

### Conversion CLI

**2D Model:**
```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 2 \
  --model 2D_versatile_fluo \
  --output ./onnx_models
```

**3D Model:**
```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 3 \
  --model 3D_demo \
  --output ./onnx_models
```

### Compiled Extension

StarDist ONNX models use a compiled C++ extension for NMS operations:

**Package:** `senoquant-stardist-ext`

**Installation:**
```bash
pip install senoquant-stardist-ext
```

**Building from source:**
```bash
pip install -U scikit-build-core
pip wheel ./stardist_ext -w ./wheelhouse
pip install ./wheelhouse/senoquant_stardist_ext-*.whl
```

### Platform Notes

- **Linux**: Recommended for ONNX conversion (stable TensorFlow builds)
- **macOS**: May have protobuf conflicts; prefer Linux for conversion
- **Windows**: Supported via CI-built wheels
