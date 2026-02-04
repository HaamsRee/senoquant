# Manual installation

This guide covers manual installation using conda, pip, and uv for users who prefer a command-line setup or are developing SenoQuant.

> **Note:** For most users, the **[installers](../user/installation.md)** are recommended as they simplify setup and ensure GPU support.

## Create an environment

In your terminal (Command Prompt/PowerShell on Windows, Terminal on macOS/Linux), create and activate a new conda environment with Python 3.11.

```bash
conda create -n senoquant python=3.11
conda activate senoquant
```

You should see `(senoquant)` at the beginning of your terminal prompt, indicating that the environment is active.

## Install uv and napari

We strongly recommend using `uv` instead of `pip` because standard pip often has difficulty solving complex dependencies. `uv` is also *much* faster.

```bash
pip install uv
uv pip install pip-system-certs
uv pip install "napari[all]"
```

> **Note:** `pip-system-certs` enables Python to use your system's certificate store for SSL verification. This helps avoid certificate errors when downloading packages or models, especially on corporate networks or systems with custom certificate authorities.

Alternatively, using standard `pip`:

```bash
pip install "napari[all]"
```

## Install SenoQuant

```bash
uv pip install senoquant
```

Alternatively, using standard `pip` (not recommended. This might be fine for napari, but often fails for SenoQuant):

```bash
pip install senoquant
```

> **Warning (Windows):** Installing via `pip`/`uv` may not pull a GPU-enabled PyTorch build on Windows. If you need GPU acceleration, use the [Windows installer](../user/installation.md#windows) instead. Or, troubleshoot PyTorch installation manually by following the [official PyTorch instructions](https://pytorch.org/get-started/locally/).

### Optional dependencies

- `uv pip install senoquant[gpu]` for optional GPU-focused extras (requires CUDA; Windows and Linux only).
- `uv pip install senoquant[all]` for full stack.

## Launch

Start napari from your terminal:

```bash
napari --with senoquant
```

> The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (a few GBs) from Hugging Face. Subsequent launches will be faster as models are cached locally.

> Make sure the terminal remains open while using napari to keep it running. The terminal also displays useful info/warning/error messages.

## Development installation

For development work, install SenoQuant from the repository in editable mode:

```bash
pip install uv
uv pip install -e .
```

This allows you to make changes to the code and see them reflected immediately without reinstalling.
