# Quantification features

Quantification features live in `src/senoquant/tabs/quantification/features`.
Each feature owns two things:

- UI controls (`build()` in a `SenoQuantFeature` subclass).
- Export logic (`export()` that writes files into a temp directory).

## How feature loading works

- `get_feature_registry()` in `src/senoquant/tabs/quantification/features/__init__.py`
  imports all submodules and collects subclasses of `SenoQuantFeature`.
- The feature picker uses each class's `feature_type` string.
- Feature type order in the UI is sorted by the class attribute `order`.
- Feature state is stored in `FeatureConfig`:
  - `feature_id` (stable id).
  - `name` (user-facing name).
  - `type_name` (feature type).
  - `data` (feature-specific payload, subclass of `FeatureData`).

## Runtime and output routing

- `QuantificationTab` builds one `FeatureUIContext` per row and instantiates a
  feature handler (`feature_handler`) from the registry.
- `QuantificationBackend.process()` calls `handler.export(temp_dir, export_format)`
  for each configured feature.
- Output files are moved into a feature-specific folder under the chosen output
  root:
  - Folder name = sanitized feature `name` (or `type_name` when name is blank).
  - Lowercase, spaces become `_`, and non-alphanumeric characters are replaced.
- If `export()` returns an empty iterable, the backend moves all files found in
  that feature's temp directory.

## Add a new quantification feature

### 1) Create a feature package

Create `src/senoquant/tabs/quantification/features/<your_feature>/` and add at
least:

- `config.py` for dataclasses.
- `feature.py` for the UI handler.
- `export.py` for file generation.

### 2) Define feature data payload

In `config.py`, define dataclasses that inherit from `FeatureData` (directly or
indirectly).

```python
from dataclasses import dataclass, field
from senoquant.tabs.quantification.features.base import FeatureData


@dataclass
class MyFeatureData(FeatureData):
    labels: list[str] = field(default_factory=list)
    enabled: bool = True
```

### 3) Implement the feature handler

In `feature.py`, subclass `SenoQuantFeature` and set a unique `feature_type`.

```python
from pathlib import Path
from senoquant.tabs.quantification.features.base import SenoQuantFeature
from .export import export_my_feature


class MyFeature(SenoQuantFeature):
    feature_type = "My feature"
    order = 30

    def build(self) -> None:
        # Build controls and persist values into self._state.data
        ...

    def export(self, temp_dir: Path, export_format: str):
        return export_my_feature(
            self._state,
            temp_dir,
            viewer=self._tab._viewer,
            export_format=export_format,
        )
```

### 4) Register feature data factory

Update `FEATURE_DATA_FACTORY` in
`src/senoquant/tabs/quantification/features/__init__.py`:

```python
FEATURE_DATA_FACTORY = {
    "Markers": MarkerFeatureData,
    "Spots": SpotsFeatureData,
    "My feature": MyFeatureData,
}
```

Without this, switching to your feature type creates a generic `FeatureData`
object and your typed config is lost.

### 5) Add batch profile serialization support

If the feature should work with Batch profile save/load, update
`src/senoquant/tabs/batch/config.py`:

- `_serialize_feature_data()` to add a case for your data class.
- `_deserialize_feature_data()` to reconstruct your data class.

If you skip this step, profiles will serialize as `{"type": "Unknown"}` and
reload without your feature settings.

### 6) Add tests

Recommended test updates:

- Registry and data factory: `tests/senoquant/tabs/quantification/features/test_registry.py`.
- Export behavior: add tests under `tests/senoquant/tabs/quantification/features/`.
- Batch profile round-trip: `tests/senoquant/tabs/batch/test_config.py`.

## Built-in export patterns (consolidated reference columns)

This section replaces the old standalone marker cross-reference document.

### Markers export

`src/senoquant/tabs/quantification/features/marker/export.py` currently writes:

- One table per selected segmentation: `<segmentation>.csv|xlsx`.
- Optional shared threshold metadata: `marker_thresholds.json` (when channels
  are configured and threshold export is enabled).

Reference columns added in marker rows:

- `file_path` (from first selected channel image metadata path, when present).
- `segmentation_type` (`nuclear` or `cytoplasmic`).
- `overlaps_with` (cross-segmentation overlap ids, `seg_name_label_id;...`).

### Spots export

`src/senoquant/tabs/quantification/features/spots/export.py` currently writes,
per selected segmentation:

- `<segmentation>_cells.csv|xlsx`.
- `<segmentation>_spots.csv|xlsx`.

Reference and relationship columns:

- `file_path` is included in both cells and spots tables.
- Cells table includes `overlaps_with` for cross-segmentation overlaps.
- If `export_colocalization` is enabled:
  - The spots table includes `colocalizes_with`.
  - The cells table includes `colocalization_event_count`.

Channel label behavior in spots export:

- Use `channel.name` (trimmed) if provided.
- Fall back to `channel.channel` when name is blank.

## Common pitfalls

- `feature_type` mismatch across class, factory key, and serialized `"type"` string.
- Returning no files from `export()` and forgetting to write files into `temp_dir`.
- Adding a new `FeatureData` subclass but not wiring Batch serialize/deserialize.
