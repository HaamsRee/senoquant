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
