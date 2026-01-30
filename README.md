# SenoQuant

![tests](https://github.com/HaamsRee/senoquant-dev/actions/workflows/tests.yml/badge.svg)

SenoQuant is a versatile Napari plugin designed for comprehensive, accurate,
and unbiased spatial quantification and prediction of senescence markers
across diverse tissue contexts.

## Documentation

Docs are built with MkDocs Material and published via GitHub Pages.

- Local preview: `pip install mkdocs-material` then `mkdocs serve`
- Build output: `mkdocs build`
- CI deploy: `.github/workflows/docs.yml`

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
  - 2D: `python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli --dim 2 --model 2D_versatile_fluo --output ./onnx_models`
  - 3D: `python -m senoquant.tabs.segmentation.stardist_onnx_utils.onnx_framework.convert.cli --dim 3 --model 3D_demo --output ./onnx_models`

### Version Notes

- Known-good Linux combo:
  - `tensorflow==2.20.0`
  - `tf2onnx==1.16.1`
  - `protobuf==6.33.4` (must be installed after TensorFlow/tf2onnx)
- If you see protobuf/runtime import errors, reinstall protobuf last.
- macOS note: some TF/protobuf builds can crash with `libc++abi` mutex errors. If that happens, try a clean conda env and prefer Linux for conversion.

## StarDist Extension (Compiled NMS)

The StarDist ONNX model uses compiled C/C++ extensions for NMS and 3D label rendering.
These are packaged as a separate wheel to keep the main plugin lightweight.

- Install from PyPI (recommended):
  - `pip install senoquant-stardist-ext`
- If you are working from source or need a custom build, build the wheel locally:
  - `pip install -U scikit-build-core`
  - `pip wheel ./stardist_ext -w ./wheelhouse`
  - `pip install ./wheelhouse/senoquant_stardist_ext-*.whl`
- Then install and run the plugin as usual:
  - `uv pip install -e .`
  - `napari`

### Wheels from CI

The GitHub Actions workflow `.github/workflows/build-stardist-ext.yml` builds
platform wheels via `cibuildwheel`. Download artifacts from the workflow run
and install the appropriate wheel for your platform:

- `pip install /path/to/senoquant_stardist_ext-*.whl`
