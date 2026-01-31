# Installation

SenoQuant targets Python 3.11 and is designed to run inside a napari environment.

## Create an environment

```bash
conda create -n senoquant python=3.11
conda activate senoquant
```

## Install napari

```bash
pip install "napari[all]"
```

Alternatively, using `uv` (faster installer):

```bash
pip install uv
uv pip install "napari[all]"
```

## Install SenoQuant

```bash
pip install senoquant
```

Alternatively, using `uv`:

```bash
uv pip install senoquant
```

Model files are downloaded automatically on first use from Hugging Face.

**Note:** The first launch of napari and the SenoQuant plugin will be slower as napari initializes and SenoQuant downloads model files (~1.3 GB) from Hugging Face. Subsequent launches will be faster as models are cached locally.

## Optional dependencies

- `pip install senoquant[gpu]` for GPU acceleration (requires CUDA; Windows and Linux only)
- `pip install senoquant[all]` for full stack

## Launch

Start napari and open the plugin:

```bash
napari
```

Then select `Plugins` -> `SenoQuant`.
