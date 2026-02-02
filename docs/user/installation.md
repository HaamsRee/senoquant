# Installation

SenoQuant targets Python 3.11 and is designed to run inside [napari](https://napari.org/stable/index.html).

## Installer (recommended)

### Windows

The **Windows installer** is the easiest and most reliable way to install SenoQuant on Windows.

1. Download the **Windows installer** (`.exe`) from the [latest GitHub Release](https://github.com/senoquant/senoquant/releases).
2. Run the installer and choose an install location (user profile locations like LocalAppData are recommended).
3. After installation completes, launch **SenoQuant** from the Start Menu or the desktop icon.

> **Note:** The installer sets up a dedicated conda environment and installs GPU-enabled PyTorch where available. This avoids the common issue where `pip` installs CPU-only PyTorch on Windows.

> The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (a few GBs) from Hugging Face. Subsequent launches will be faster as models are cached locally.

### macOS

The **macOS installer** provides a native PKG installer that sets up SenoQuant with all dependencies.

1. Download the **macOS installer** (`.pkg`) from the [latest GitHub Release](https://github.com/senoquant/senoquant/releases).
2. Double-click the PKG file and follow the installation prompts.
3. The app installs to `~/Applications/SenoQuant.app`.
4. Launch **SenoQuant** from Spotlight, Launchpad, or your Applications folder.

> **Note:** On first launch, a Terminal window opens showing installation progress. The initial setup creates a Python environment and installs napari, PyTorch, and SenoQuant dependencies. This may take **5-10 minutes** depending on your internet connection. Subsequent launches will be much faster.

> The Python environment and logs are stored in `~/Library/Application Support/SenoQuant/`, while the app bundle remains at `~/Applications/SenoQuant.app`.

**Architecture Support:**
- **Apple Silicon (M1/M2/M3)**: Includes MPS (Metal Performance Shaders) acceleration for improved performance
- **Intel Macs**: CPU-only operation

### Linux

Under construction

## Manual installation (conda/pip/uv)

For manual installation using conda, pip, and uv—whether you're on Windows, macOS, Linux, or doing development work—see the [Installation guide in the Developer Guide](../../developer/installation/).

> **Warning:** Manual installations via `pip`/`uv` may not pull a GPU-enabled PyTorch build on Windows. If you need GPU acceleration, use the Windows Installer above. Or, troubleshoot PyTorch installation manually by following the [official PyTorch instructions](https://pytorch.org/get-started/locally/).
