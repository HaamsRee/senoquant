# Installation

SenoQuant targets Python 3.11 and is designed to run inside [napari](https://napari.org/stable/index.html).

## System requirements

Before installing, make sure your system meets these requirements:

- A 64-bit operating system.
- A stable internet connection for first-time setup and model downloads.
- Enough free disk space for the Python environment, dependencies, and cached models (several GB).

### Platform support

- **Windows installer**: 64-bit Windows (`x64`).
- **macOS installer**: macOS 10.15 or later.
- **macOS hardware**: Apple Silicon and Intel are both supported.
- **Linux**: Installer support is under construction.

### Runtime notes

- **Manual installs** require Python 3.11.
- **Windows** can use GPU acceleration when a compatible PyTorch/CUDA setup is available.
- **Apple Silicon** can use MPS acceleration.
- **Intel Macs** currently run CPU-only.

### Recommended hardware

These are practical recommendations for smooth use. They are not strict hard limits.

- **CPU**: 8 cores (or better) is recommended. 4 cores is workable for small 2D datasets.
- **System RAM**:
  - 16 GB minimum for light 2D work.
  - 32 GB recommended for routine multi-channel analysis.
  - 64 GB or more recommended for large 3D stacks and batch processing.
- **Discrete GPU (Windows/Linux, recommended)**:
  - NVIDIA GPU with CUDA support.
  - 8 GB VRAM recommended for most 2D workflows.
  - 12 GB or more VRAM recommended for larger images, 3D workflows, or high-throughput batch runs.
- **Storage**: SSD strongly recommended, with at least 50-100 GB free for environments, model cache, and outputs.

Reference build targets:

- **Good baseline workstation**: 8-core CPU, 32 GB RAM, NVIDIA RTX-class GPU with 8 GB VRAM.
- **Heavy 3D or high-throughput batch workstation**: 12+ core CPU, 64 GB RAM, NVIDIA RTX-class GPU with 12-24 GB VRAM.

## Installer (recommended)

### Windows

The **Windows installer** is the easiest and most reliable way to install SenoQuant on Windows.

1. Download the **Windows installer** (`.exe`) from the [latest GitHub Release](https://github.com/HaamsRee/senoquant/releases).
2. Run the installer and choose an install location (user profile locations like LocalAppData are recommended).
3. After installation completes, launch **SenoQuant** from the Start Menu or the desktop icon.

> **Note:** The installer sets up a dedicated conda environment and installs GPU-enabled PyTorch where available. This avoids the common issue where `pip` installs CPU-only PyTorch on Windows.

> The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (a few GBs) from Hugging Face. Subsequent launches will be faster as models are cached locally.

### macOS

The **macOS installer** provides a native PKG installer that sets up SenoQuant with all dependencies.

1. Download the **macOS installer** (`.pkg`) from the [latest GitHub Release](https://github.com/HaamsRee/senoquant/releases).
2. Double-click the PKG file and follow the installation prompts.
3. The app installs to `~/Applications/SenoQuant.app`.
4. Launch **SenoQuant** from Spotlight, Launchpad, or your Applications folder.

> **Note:** On first launch, a Terminal window opens showing installation progress. The initial setup creates a Python environment and installs napari, PyTorch, and SenoQuant dependencies. This may take **5-10 minutes** depending on your internet connection. Subsequent launches will be much faster.

> The Python environment and logs are stored in `~/Library/Application Support/SenoQuant/`, while the app bundle remains at `~/Applications/SenoQuant.app`.

**Architecture Support:**

- **Apple Silicon (M1/M2/M3)**: Includes MPS (Metal Performance Shaders) acceleration for improved performance.
- **Intel Macs**: CPU-only operation.

### Linux

Under construction

## Manual installation (conda/pip/uv)

For manual installation using conda, pip, and uv—whether you're on Windows, macOS, Linux, or doing development work—see the [Installation guide in the Developer Guide](../../developer/installation/).

> **Warning:** Manual installations via `pip`/`uv` may not pull a GPU-enabled PyTorch build on Windows. If you need GPU acceleration, use the Windows Installer above. Or, troubleshoot PyTorch installation manually by following the [official PyTorch instructions](https://pytorch.org/get-started/locally/).
