# SenoQuant

![tests](https://github.com/HaamsRee/senoquant/actions/workflows/tests.yml/badge.svg)
[![PyPI version](https://badge.fury.io/py/senoquant.svg)](https://badge.fury.io/py/senoquant)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

SenoQuant is a versatile [napari](https://napari.org/stable/index.html) plugin designed for comprehensive, accurate,
and unbiased spatial quantification and prediction of senescence markers
across diverse tissue contexts.

## Features

- Read microscopy formats via BioIO, including OME-TIFF, ND2, LIF, CZI, Zarr, and more.
- Segment nuclei and cytoplasm with built-in models, including StarDist ONNX, Cellpose SAM, and morphology-based models.
- Detect punctate spots with a U-FISH-based detector.
- Quantify marker intensity, morphology, spot counts, and spot colocalization.
- Generate visualization outputs from quantification tables (Spatial Plot, UMAP, and Double Expression).
- Run batch workflows across folders with multi-scene support.
- Save/load reusable Segmentation, Spots, and Batch settings for reproducibility.
- *Upcoming*: Integrate custom models for predicting senescence markers.

## Installation

### Installer (recommended)

#### Windows

Download the Windows installer (`.exe`) from the [latest release](https://github.com/HaamsRee/senoquant/releases/latest).

#### macOS

Download the macOS installer (`.pkg`) from the [latest release](https://github.com/HaamsRee/senoquant/releases/latest).

#### Linux

Installer support for Linux is under construction.

### Manual installation

For conda/pip/uv setup, see the [developer installation guide](https://haamsree.github.io/senoquant/developer/installation/).

## Quick start

Use the documentation workflow for the most up-to-date instructions.

- Start with the [installation guide](https://haamsree.github.io/senoquant/user/installation/).
- Follow the [quick start guide](https://haamsree.github.io/senoquant/user/quickstart/).
- Then use tab-specific guides for [segmentation](https://haamsree.github.io/senoquant/user/segmentation/), [spots](https://haamsree.github.io/senoquant/user/spots/), [quantification](https://haamsree.github.io/senoquant/user/quantification/), [visualization](https://haamsree.github.io/senoquant/user/visualization/), [batch](https://haamsree.github.io/senoquant/user/batch/), and [settings](https://haamsree.github.io/senoquant/user/settings/).

## Documentation

Full documentation is available at [https://haamsree.github.io/senoquant/](https://haamsree.github.io/senoquant/).

- [Installation guide](https://haamsree.github.io/senoquant/user/installation/).
- [Quick start tutorial](https://haamsree.github.io/senoquant/user/quickstart/).
- [Segmentation models](https://haamsree.github.io/senoquant/user/segmentation/).
- [Spot detection](https://haamsree.github.io/senoquant/user/spots/).
- [Quantification features](https://haamsree.github.io/senoquant/user/quantification/).
- [Visualization tab](https://haamsree.github.io/senoquant/user/visualization/).
- [Batch processing](https://haamsree.github.io/senoquant/user/batch/).
- [Settings persistence](https://haamsree.github.io/senoquant/user/settings/).
- [API reference](https://haamsree.github.io/senoquant/api/).

## Development

See the [contributing guide](https://haamsree.github.io/senoquant/developer/contributing/) for development setup instructions.

## How to cite

If you use SenoQuant in your research, please cite it using the metadata in `CITATION.cff`.

On GitHub, open the repository page and click `Cite this repository` in the right sidebar to copy a formatted citation.

## Acknowledgements

SenoQuant builds on and integrates excellent open-source projects.

- [napari](https://napari.org/).
- [StarDist](https://github.com/stardist/stardist).
- [Cellpose](https://github.com/MouseLand/cellpose).
- [U-FISH](https://github.com/UFISH-Team/U-FISH).
- [BioIO](https://github.com/bioio-devs/bioio).
