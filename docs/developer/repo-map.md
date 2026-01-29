# Repo Map

High-level layout of the repository:

- `src/senoquant/` - Python package root.
  - `_widget.py` - main napari widget.
  - `_reader.py` - napari reader entrypoint.
  - `napari.yaml` - plugin declaration.
  - `reader/` - BioIO-based reader implementation.
  - `tabs/` - UI tabs (segmentation, spots, quantification, batch, settings).
- `stardist_ext/` - compiled StarDist extension source.
- `tests/` - tests (currently empty).
- `wheelhouse/` - local wheel output for the extension build.
- `res/` - resource assets (if present).

Tab subdirectories follow a consistent structure:

- `frontend.py` - Qt UI widgets and event handling.
- `backend.py` - processing logic and discovery.
- `models/` - model or detector implementations plus metadata.
