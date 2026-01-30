# Installation

SenoQuant targets Python 3.11 and is designed to run inside a napari
environment. The project does not pin napari in its runtime dependencies,
so you need to install napari separately.

## Create an environment

```bash
conda create -n senoquant python=3.11
conda activate senoquant
```

## Install napari

```bash
pip install "napari[all]"
```

## Install SenoQuant from source

```bash
pip install -e .
```

If you prefer `uv` (fast installer):

```bash
pip install uv
uv pip install "napari[all]"
uv pip install -e .
```

## Optional dependencies

The project defines optional dependency groups in `pyproject.toml`:

- `.[distributed]` for dask support.
- `.[gpu]` for GPU extras.
- `.[all]` for the full stack (napari + optional deps).

Example:

```bash
pip install -e ".[all]"
```

## StarDist extension (compiled)

StarDist ONNX inference uses a compiled extension for NMS and 3D label
rendering. Install it from PyPI:

```bash
pip install senoquant-stardist-ext
```

If you are working from source or need a custom build, build the wheel locally:

```bash
pip install -U scikit-build-core
pip wheel ./stardist_ext -w ./wheelhouse
pip install ./wheelhouse/senoquant_stardist_ext-*.whl
```

## Launch

Start napari and open the plugin:

```bash
napari
```

Then select `Plugins` -> `SenoQuant`.
