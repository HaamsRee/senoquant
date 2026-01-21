# SenoQuant

A minimal napari plugin scaffold using qtpy.

## Development

- Create a virtual environment
- Install with `pip install -e .`
- Note: the default `napari-bioio-reader` (bioformats) can fail on very large images.
  Installing a dedicated reader plugin may help (e.g., `pip install bioio-ome-tiff`).
- Run napari and open the plugin widget from the Plugins menu
