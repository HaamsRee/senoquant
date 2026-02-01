# SenoQuant

![tests](https://github.com/HaamsRee/senoquant-dev/actions/workflows/tests.yml/badge.svg)
[![PyPI version](https://badge.fury.io/py/senoquant.svg)](https://badge.fury.io/py/senoquant)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)

SenoQuant is a versatile Napari plugin designed for comprehensive, accurate,
and unbiased spatial quantification and prediction of senescence markers
across diverse tissue contexts.

## Features

- **Multi-Model Segmentation**: Nuclear and cytoplasmic segmentation with 5 built-in models
   - StarDist ONNX (2D/3D)
   - Cellpose SAM
   - Morphological operations (dilation, perinuclear rings)
- **Spot Detection**: Detect and quantify punctate senescence markers
   - Undecimated B3-spline wavelet (UDWT)
   - Rotational morphological processing (RMP)
- **Quantification**: Extract intensity, morphology, and spot metrics
   - Per-cell marker intensities
   - Morphological descriptors
   - Spot counting and colocalization
- **Batch Processing**: Automated analysis of entire image folders
   - Profile save/load for reproducibility
   - Multi-scene file support
- **File Format Support**: Microscopy formats via BioIO
   - OME-TIFF, ND2, LIF, CZI, Zarr, and more

## Installation

### Windows (Recommended)

**Download the SenoQuant Installer (.exe)** from the [latest release](https://github.com/HaamsRee/senoquant-dev/releases/latest).

The installer automatically sets up a Python environment with napari, SenoQuant, and GPU PyTorch support. Simply run the `.exe` and follow the prompts. After installation, launch SenoQuant from the Start menu.

### macOS & Linux

🚧 **Installers for macOS and Linux are under construction.** For command-line installation using `pip` or `uv`, see the [Installation Guide](https://haamsree.github.io/senoquant-dev/user/installation/).

**Note:** The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (~1.3 GB) from Hugging Face. Subsequent launches will be faster as models are cached locally.

## Quick Start

1. **Launch SenoQuant:**  
    Click "SenoQuant" from the Start menu (Windows installer)

2. **Open your image:**  
    File → Open File(s)... → Select your image. Or drag-and-drop into napari.

3. **Open SenoQuant plugin:**  
    Should automatically open. If not, Plugins → SenoQuant

4. **Run segmentation:**  
    Segmentation tab → Select nuclear channel → Choose model → Run

5. **Detect spots (optional):**  
    Spots tab → Select channel → Choose detector → Run

6. **Export quantification:**  
    Quantification tab → Configure features → Process

7. **Batch process (optional):**  
    Batch tab → Configure settings → Run batch

For command-line launch and installation methods, see the [Quick Start Guide](https://haamsree.github.io/senoquant-dev/user/quickstart/).

## Documentation

Full documentation is available at [https://haamsree.github.io/senoquant-dev/](https://haamsree.github.io/senoquant-dev/)

- [Installation Guide](https://haamsree.github.io/senoquant-dev/user/installation/)
- [Quick Start Tutorial](https://haamsree.github.io/senoquant-dev/user/quickstart/)
- [Segmentation Models](https://haamsree.github.io/senoquant-dev/user/segmentation/)
- [Spot Detection](https://haamsree.github.io/senoquant-dev/user/spots/)
- [Quantification Features](https://haamsree.github.io/senoquant-dev/user/quantification/)
- [Batch Processing](https://haamsree.github.io/senoquant-dev/user/batch/)
- [API Reference](https://haamsree.github.io/senoquant-dev/api/)

## Development

See the [Contributing Guide](https://haamsree.github.io/senoquant-dev/developer/contributing/) for development setup instructions.

