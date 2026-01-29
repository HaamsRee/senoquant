# Architecture

This repo is a napari plugin organized around a Qt widget and a set of
tab modules.

## Entry points

- `src/senoquant/napari.yaml` declares the napari widget and reader.
- `src/senoquant/_widget.py` defines `SenoQuantWidget` and registers the
  tabbed UI.
- `src/senoquant/_reader.py` exposes the reader entrypoint.

## UI structure

The main widget (`SenoQuantWidget`) composes five tabs:

- Segmentation (`src/senoquant/tabs/segmentation`)
- Spots (`src/senoquant/tabs/spots`)
- Quantification (`src/senoquant/tabs/quantification`)
- Batch (`src/senoquant/tabs/batch`)
- Settings (`src/senoquant/tabs/settings`)

Each tab follows a frontend/backend split:

- `frontend.py` builds the Qt widgets and handles UI events.
- `backend.py` performs the model discovery or processing logic.

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
3. Run spot detection per selected channels.
4. Run quantification using a lightweight viewer shim.
5. Write masks and quantification outputs to disk.

## Settings storage

The Settings tab uses a simple backend (`SettingsBackend`) to store
preferences like model preloading.
