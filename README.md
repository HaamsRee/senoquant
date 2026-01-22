# SenoQuant

A minimal napari plugin scaffold using qtpy.

## Development

- Create a conda environment with Python 3.11.
- `pip install uv` (fast alternative to pip)
- `uv pip install "napari[all]"`
- `uv pip install -e .`
- Note: bioformats-based readers can fail on very large images. Installing
  dedicated reader plugins may help (e.g., `pip install bioio-ome-tiff`).
- Run napari and open the plugin widget from the Plugins menu

## StarDist ONNX Converter

- Create and activate a conda environment with Python 3.11.
- `pip install uv`
- `uv pip install tensorflow tf2onnx`
- Force protobuf after TensorFlow and tf2onnx:
  - `uv pip install --upgrade "protobuf>=6.33.4"`
- Ensure the package is installed (see Development section): `uv pip install -e .`
- Convert a pretrained model:
  - 2D: `python -m senoquant.tabs.segmentation.models.stardist_onnx.onnx_framework.convert.cli --dim 2 --model 2D_versatile_fluo --output ./onnx_models`
  - 3D: `python -m senoquant.tabs.segmentation.models.stardist_onnx.onnx_framework.convert.cli --dim 3 --model 3D_demo --output ./onnx_models`

### Version Notes

- Known-good Linux combo:
  - `tensorflow==2.20.0`
  - `tf2onnx==1.16.1`
  - `protobuf==6.33.4` (must be installed after TensorFlow/tf2onnx)
- If you see protobuf/runtime import errors, reinstall protobuf last.
- macOS note: some TF/protobuf builds can crash with `libc++abi` mutex errors. If that happens, try a clean conda env and prefer Linux for conversion.
