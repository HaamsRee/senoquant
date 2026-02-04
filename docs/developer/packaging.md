# Packaging and releases

SenoQuant is a setuptools-based Python package with a separate compiled
extension for StarDist NMS and 3D label rendering. The project provides
native installers for Windows and macOS.

## Core package

- Metadata lives in `pyproject.toml`.
- Version is centralized in `pyproject.toml` and read by all build systems.
- The plugin exposes napari entry points via `src/senoquant/napari.yaml`.

## Native installers

SenoQuant provides native installers that bundle the application with all dependencies:

- **Windows**: Inno Setup-based `.exe` installer (see [Installers documentation](installer.md#windows-installer)).
- **macOS**: PKG installer targeting `~/Applications` (see [Installers documentation](installer.md#macos-installer)).

Both installers:

- Include a micromamba-based Python 3.11 environment.
- Install napari, PyTorch, and SenoQuant on first launch.
- Are built automatically via GitHub Actions and attached to releases.

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
