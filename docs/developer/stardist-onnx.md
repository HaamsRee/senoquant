# StarDist ONNX conversion

This guide documents the StarDist-to-ONNX conversion utility used by the
default StarDist segmentation models.

## Location

Conversion code lives under:

- `src/senoquant/tabs/segmentation/stardist_onnx_utils/onnx_framework/convert/`

Main entry points:

- `convert_pretrained_2d(...)`
- `convert_pretrained_3d(...)`
- `convert_model_to_onnx(...)`
- CLI module: `convert/cli.py`

## Prerequisites

Conversion requires TensorFlow + tf2onnx in your environment.

Recommended extras for conversion workflows:

- `tensorflow`
- `tf2onnx`
- compatible `protobuf` (if conversion errors reference protobuf mismatches)

## CLI usage

The converter is currently exposed as a Python module CLI.

Convert pretrained 2D model:

```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 2d \
  --model 2D_versatile_fluo \
  --output ./onnx_models \
  --opset 18
```

Convert pretrained 3D model:

```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli \
  --dim 3d \
  --model 3D_demo \
  --output ./onnx_models \
  --opset 18
```

`--output` can be either:

- a directory (auto filename is generated), or
- a full `.onnx` file path.

### Converter CLI flags (`convert.cli`)

Command:

`python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli`

| Argument | Type | Default | What it does |
| --- | --- | --- | --- |
| `--dim` | choice: `2`, `3`, `2d`, `3d` | `2d` | Selects 2D vs 3D StarDist model conversion path. |
| `--model` | string | `None` | Pretrained model alias or local StarDist model directory path. If omitted, uses built-in default model for selected `--dim`. |
| `--output` | path | `.` | Output destination. Directory => auto-generated filename; `.onnx` path => exact output file. |
| `--opset` | int | `18` | ONNX opset version used during export via `tf2onnx`. |

Default model mapping when `--model` is omitted:

- `--dim 2d` / `2` -> `2D_versatile_fluo`
- `--dim 3d` / `3` -> `3D_demo`

## Python API usage

```python
from senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert import (
    convert_pretrained_2d,
    convert_pretrained_3d,
)

path2d = convert_pretrained_2d("2D_versatile_fluo", "./onnx_models", opset=18)
path3d = convert_pretrained_3d("3D_demo", "./onnx_models", opset=18)
print(path2d, path3d)
```

You can also pass a StarDist model instance to `convert_model_to_onnx(...)`.

## Output filenames and placement

When `--output` points to a directory, generated filenames follow:

- `stardist2d_<model_name>.onnx`
- `stardist3d_<model_name>.onnx`

For automatic discovery by SenoQuant default models, place ONNX files in the
model folders, preferably:

- `src/senoquant/tabs/segmentation/models/default_2d/onnx_models/default_2d.onnx`
- `src/senoquant/tabs/segmentation/models/default_3d/onnx_models/default_3d.onnx`

## Optional inspection helpers

After conversion, you can inspect model IO/divisibility:

```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.cli \
  ./onnx_models/stardist2d_2D_versatile_fluo.onnx \
  --ndim 2
```

And estimate receptive field/overlap:

```bash
python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.rf_cli \
  ./onnx_models/stardist2d_2D_versatile_fluo.onnx \
  --ndim 2 --shape 256 256
```

### Inspect CLI flags (`inspect.cli`)

Command:

`python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.cli`

| Argument | Type | Default | What it does |
| --- | --- | --- | --- |
| `model` | path (positional) | required | Path to the ONNX model to inspect. |
| `--ndim` | choice: `2`, `3` | `None` | Optional dimensionality hint for `div_by` inference. |

### Receptive-field CLI flags (`inspect.rf_cli`)

Command:

`python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.inspect.rf_cli`

| Argument | Type | Default | What it does |
| --- | --- | --- | --- |
| `model` | path (positional) | required | Path to the ONNX model. |
| `--ndim` | choice: `2`, `3` | `None` | Optional dimensionality hint for receptive-field estimation. |
| `--shape` | int list | `None` | Spatial probe size, e.g. `--shape 256 256` (2D) or `--shape 64 64 64` (3D). |
| `--eps` | float | `0.0` | Sensitivity threshold for numerical change detection during RF probing. |

## Troubleshooting

- **`TensorFlow is required to export StarDist models.`**

    - Install TensorFlow in the active env.

- **`tf2onnx is required to export StarDist models.`**

    - Install `tf2onnx` in the same env.

- **protobuf-related conversion errors**

    - Reinstall/align protobuf with your TensorFlow/tf2onnx stack.

- **Runtime inference errors after conversion**

    - Verify model IO with `inspect.cli`.
    - Verify output model path matches SenoQuant model lookup conventions.