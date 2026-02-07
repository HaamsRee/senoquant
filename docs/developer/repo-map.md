# Repo map

This page summarizes the current repository layout and where core behavior is implemented.

## Top-level folders

- `src/senoquant/`: package source.
- `tests/`: pytest suite.
- `docs/`: MkDocs docs (`user/`, `developer/`, `api/`).
- `stardist_ext/`: compiled StarDist extension source/package.
- `_vendor/ufish/`: vendored U-FISH code used by spot detection support.
- `installer/`: installer build assets and scripts.
- `res/`: extra resources used by packaging/install flows.

## Package entry points (`src/senoquant`)

- `napari.yaml`: napari plugin registration (widget + reader).
- `__init__.py`: exports plugin symbols.
- `_widget.py`: main tabbed widget (`SenoQuantWidget`) wiring all tabs.
- `_reader.py`: napari reader entrypoint.
- `reader/core.py`: BioIO-backed reader implementation (scene selection, channel splitting, metadata).
- `utils/utils.py`: shared utility helpers.
- `utils/settings_bundle.py`: unified `senoquant.settings` envelope helpers.
- `utils/model_details.schema.json`: JSON Schema for model/detector `details.json` manifests.
- `utils/model_details_schema.py`: manifest validation helpers used by segmentation/spots base classes.

## Tab modules (`src/senoquant/tabs`)

- `segmentation/`: segmentation tab UI/backend and segmentation models.
- `segmentation/_frontend/`: split frontend mixins and widgets used by segmentation tab.
- `segmentation/models/`: built-in models (`default_2d`, `default_3d`, `cpsam`, `nuclear_dilation`, `perinuclear_rings`).
- `segmentation/stardist_onnx_utils/`: StarDist runtime helpers, conversion/runtime support, vendored StarDist/CSBDeep compatibility code.
- `spots/`: spots tab UI/backend and detector orchestration.
- `spots/models/`: built-in detectors (`rmp`, `ufish`) plus shared detector base classes.
- `quantification/`: quantification tab UI/backend.
- `quantification/features/`: feature system (`Markers`, `Spots`) with per-feature config/UI/export modules.
- `visualization/`: visualization tab UI/backend.
- `visualization/plots/`: plot handler system (`Spatial Plot`, `UMAP`, `Double Expression`).
- `batch/`: batch UI/backend/config/io/layer shims.
- `settings/`: Settings tab save/load orchestration.

## Common tab patterns

- `frontend.py`: Qt widgets, signal wiring, and user interactions.
- `backend.py`: processing logic and discovery/orchestration.
- `models/<name>/details.json`: metadata-driven settings schema for model/detector UI.
- `models/<name>/model.py`: runtime implementation class.

## Test layout highlights (`tests/senoquant`)

- `tabs/test_ui_smoke.py`: tab/widget smoke tests.
- `tabs/segmentation/`: frontend/backend/model tests for segmentation.
- `tabs/spots/`: frontend/backend/detector/filter tests for spots.
- `tabs/quantification/`: backend + feature export and UI tests.
- `tabs/visualization/`: backend/plot registry/handler tests.
- `tabs/batch/`: config/backend/io/frontend integration tests.
- `tabs/settings/`: settings backend/frontend round-trip tests.
