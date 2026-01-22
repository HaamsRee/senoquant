# SenoQuant

A minimal napari plugin scaffold using qtpy.

## Development

- Create a conda environment with Python 3.11.
- `pip install uv` (fast alternative to pip)
- `uv pip install "napari[all]"`
- `uv pip install -e .`
- Note: bioformats-based readers can fail on very large images. Installing
  dedicated reader plugins may help (e.g., `pip install bioio-ome-tiff`).
- Run napari and open the plugin widget from the Plugins menu
