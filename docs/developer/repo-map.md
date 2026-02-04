# Repo map

High-level layout of the repository:

- `src/senoquant/` - package root.
  - `_widget.py` - main tabbed napari widget (`SenoQuantWidget`).
  - `_reader.py` + `reader/` - BioIO-backed napari reader pipeline.
  - `napari.yaml` - plugin command/widget/reader registration.
  - `tabs/` - plugin tabs:
    - `segmentation/`.
    - `spots/`.
    - `quantification/`.
    - `visualization/`.
    - `batch/`.
    - `settings/`.
- `tests/` - pytest suite (tab UIs, backends, exports, reader, model helpers).
- `docs/` - MkDocs content (`user/`, `developer/`, `api/`).
- `stardist_ext/` - compiled StarDist extension source.
- `wheelhouse/` - local wheel artifacts (optional, build output).
- `res/` - extra resources (optional).

Common tab layout:

- `frontend.py` - Qt widgets and UI event handling.
- `backend.py` - pure logic, discovery, and processing orchestration.
- `models/` (where applicable) - model/detector folders with `details.json`
  and optional `model.py`.
