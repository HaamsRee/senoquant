# Segmentation

The Segmentation tab provides two sections:

- Nuclear segmentation
- Cytoplasmic segmentation

Each section lets you select an image layer, pick a model, and tune model
settings. Model settings are defined by the model's `details.json` file
and are rendered dynamically in the UI.

## Model settings

Each model exposes a list of settings with metadata such as:

- `key`: setting identifier used internally
- `label`: UI label
- `type`: `int`, `float`, or `bool`
- `default`, `min`, `max`, `decimals`
- `enabled_by` / `disabled_by` to control conditional UI enabling

## Available models

| Model | Description | Nuclear | Cytoplasmic | Cytoplasmic input modes | Nuclear optional |
| --- | --- | --- | --- | --- | --- |
| `cpsam` | Placeholder details for the cpsam segmentation model | Yes | Yes | `cytoplasmic`, `nuclear+cytoplasmic` | Yes |
| `cyto_only` | Placeholder details for a cytoplasmic-only model | No | Yes | `cytoplasmic` | Yes |
| `stardist_2d` | StarDist 2D nuclear segmentation using ONNX runtime | Yes | No | - | - |
| `stardist_3d` | StarDist 3D nuclear segmentation using ONNX runtime | Yes | No | - | - |
| `stardist_mod_2d` | StarDist MOD 2D nuclear segmentation using ONNX runtime | Yes | No | - | - |

## Output layers

- Nuclear segmentation outputs `<image layer>_nuclear_labels`.
- Cytoplasmic segmentation outputs `<image layer>_cyto_labels`.
- Labels layers are created with a contour value of 2.

## Preloading models

If `Preload segmentation models on startup` is enabled in Settings,
SenoQuant instantiates all discovered segmentation models when the tab
loads. This can reduce the first-run latency for models.

## Settings reference

### cpsam

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `diameter` | float | 30.0 | 0.1 - 1000.0 | - |
| `flow_threshold` | float | 0.4 | 0.0 - 2.0 | - |
| `cellprob_threshold` | float | 0.0 | -6.0 - 6.0 | - |
| `n_iterations` | int | 0 | 0 - 9999 | - |
| `use_3d` | bool | false | - | - |
| `normalize` | bool | true | - | - |

### cyto_only

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `min_size` | float | 50.0 | 0.0 - 500.0 | - |

### stardist_2d

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `object_diameter_px` | float | 30.0 | 1.0 - 500.0 | - |
| `prob_thresh` | float | 0.479071 | 0.0 - 1.0 | - |
| `nms_thresh` | float | 0.3 | 0.0 - 1.0 | - |
| `normalize` | bool | true | - | - |
| `pmin` | float | 1.0 | 0.0 - 100.0 | Enabled when `normalize` is true. |
| `pmax` | float | 99.8 | 0.0 - 100.0 | Enabled when `normalize` is true. |

### stardist_3d

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `object_diameter_px` | float | 30.0 | 1.0 - 500.0 | - |
| `prob_thresh` | float | 0.707933 | 0.0 - 1.0 | - |
| `nms_thresh` | float | 0.3 | 0.0 - 1.0 | - |
| `normalize` | bool | true | - | - |
| `pmin` | float | 1.0 | 0.0 - 100.0 | Enabled when `normalize` is true. |
| `pmax` | float | 99.8 | 0.0 - 100.0 | Enabled when `normalize` is true. |

### stardist_mod_2d

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `object_diameter_px` | float | 30.0 | 1.0 - 500.0 | - |
| `prob_thresh` | float | 0.496187 | 0.0 - 1.0 | - |
| `nms_thresh` | float | 0.3 | 0.0 - 1.0 | - |
| `normalize` | bool | true | - | - |
| `pmin` | float | 1.0 | 0.0 - 100.0 | Enabled when `normalize` is true. |
| `pmax` | float | 99.8 | 0.0 - 100.0 | Enabled when `normalize` is true. |
