# Quantification Features

Quantification features live under `src/senoquant/tabs/quantification/features`.
Each feature provides UI controls and export logic.

## Feature registry

Feature classes are discovered dynamically:

- `get_feature_registry()` walks submodules and finds subclasses of
  `SenoQuantFeature`.
- Each feature must define a `feature_type` string (used in the UI).
- Registry ordering uses the class attribute `order`.

## Core classes

- `FeatureConfig`: configuration for a feature instance (id, name, type, data).
- `FeatureData`: base class for feature-specific configuration payloads.
- `SenoQuantFeature`: base class that builds UI and exports outputs.

## Adding a new feature

1. Create a new module under `features/<your_feature>`.
2. Define a `FeatureData` subclass to hold config state.
3. Define a `SenoQuantFeature` subclass with:
   - `feature_type` string
   - `order` integer (optional)
   - `build()` UI implementation
   - `export()` implementation (writes files into `temp_dir`)
4. If you created a new `FeatureData` subclass, add it to
   `FEATURE_DATA_FACTORY` in `features/__init__.py` so the UI can build
   default data instances.

## Export routing

`QuantificationBackend.process()` calls each feature's `export()` method
and then moves outputs into a per-feature folder. If `export()` returns an
empty iterable, all files in the temporary directory are moved.

## Marker Feature

The Marker feature is implemented in `features/marker/` and measures channel
intensity and morphological properties within segmentation labels.

### Architecture

- `config.py`: Configuration dataclasses (`MarkerFeatureData`)
- `export.py`: Main export pipeline (coordinates centroid, intensity, and
  morphology extraction)
- `morphology.py`: Morphological descriptor extraction from regionprops
- `thresholding.py`: Channel threshold handling

### Morphological descriptors

Morphological descriptors are extracted via `morphology.add_morphology_columns()`
and include:

**2D images:**
- Area, perimeter, circularity, eccentricity, solidity, extent
- Feret diameter, major/minor axis lengths, orientation
- Aspect ratio (derived from axes)

**3D images:**
- Volume (renamed from area), morphological properties degrade to volume only
- No perimeter or derived shape metrics (regionprops limitation)

All properties are float-valued and prefixed with `morph_`. Physical
measurements (µm² for 2D area, µm³ for 3D volume) are added when pixel
sizes are available.

### Extending marker export

To add new intensity metrics or post-processing:

1. Edit `export.py` and add computation to the `_process_rows()` pipeline.
2. Ensure each row dict is updated with the new column(s).
3. Add column names to the header lists for CSV/XLSX generation.
