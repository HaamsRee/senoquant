# Packaging & Releases

SenoQuant is a setuptools-based Python package with a separate compiled
extension for StarDist NMS and 3D label rendering.

## Core package

- Metadata lives in `pyproject.toml`.
- The plugin exposes napari entry points via `src/senoquant/napari.yaml`.

## StarDist extension

Source for the compiled extension lives in `stardist_ext/`.
The extension is published to PyPI as `senoquant-stardist-ext`.
To build the wheel locally (for development or custom builds):

```bash
pip install -U scikit-build-core
pip wheel ./stardist_ext -w ./wheelhouse
```

Install the generated wheel:

```bash
pip install ./wheelhouse/senoquant_stardist_ext-*.whl
```

The main package depends on `senoquant-stardist-ext`, so distribution
pipelines should ensure wheels are built for target platforms and uploaded
to PyPI.
