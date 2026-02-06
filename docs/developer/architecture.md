# Architecture

This repo is a napari plugin organized around a Qt widget and a set of
tab modules.

## Entry points

- `src/senoquant/napari.yaml` declares the napari widget and reader.
- `src/senoquant/_widget.py` defines `SenoQuantWidget` and registers the
  tabbed UI.
- `src/senoquant/_reader.py` exposes the reader entrypoint.

## UI structure

The main widget (`SenoQuantWidget`) composes six tabs:

- Segmentation (`src/senoquant/tabs/segmentation`).
- Spots (`src/senoquant/tabs/spots`).
- Quantification (`src/senoquant/tabs/quantification`).
- Visualization (`src/senoquant/tabs/visualization`).
- Batch (`src/senoquant/tabs/batch`).
- Settings (`src/senoquant/tabs/settings`).

Each tab follows a frontend/backend split:

- `frontend.py` builds the Qt widgets and handles UI events.
- `backend.py` performs the model discovery or processing logic.
- Segmentation additionally uses `segmentation/_frontend/` mixins to keep UI
  code split across smaller modules.

## Reader pipeline

The reader implementation lives in `src/senoquant/reader/core.py` and
relies on BioIO to open files. The reader:

- Validates the file via `BioImage.determine_plugin`.
- Iterates scenes and channels to create napari layers.
- Applies a fixed colormap cycle for channel display.

## Batch pipeline

Batch processing is orchestrated by `BatchBackend` in
`src/senoquant/tabs/batch/backend.py`. The flow is:

1. Enumerate input files and resolve channel indices.
2. Run segmentation (nuclear/cytoplasmic) as configured.
3. Run spot detection per selected channels, then apply optional
   diameter-based spot filtering.
4. Run quantification using a lightweight viewer shim.
5. Write masks and quantification outputs to disk.
6. Persist `senoquant_settings.json` in the batch output root with the
   effective `batch_job` configuration.

## Settings storage

The Settings tab uses `SettingsBackend` to read/write unified
`senoquant.settings` JSON bundles. These bundles can include:

- `feature` payloads for tab-level settings snapshots.
- `batch_job` payloads compatible with batch config serialization.
- `segmentation_runs` payloads produced by quantification exports.

### Cross-tab settings orchestration

`SenoQuantWidget` instantiates Segmentation, Spots, Batch, and Settings tabs
as shared objects. Settings uses these references to:

- Export segmentation and spots configuration into `feature`.
- Export batch state into `batch_job`.
- Restore those states when loading a bundle.

Quantification settings are currently not restored by the Settings tab.
