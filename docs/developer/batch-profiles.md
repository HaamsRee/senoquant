# Batch settings bundles

This page replaces the old “Batch profiles” workflow.

Batch settings are now serialized in the unified `senoquant.settings` bundle
format, shared across tabs and exports.

## Current behavior

- The **Batch tab UI no longer provides Load/Save profile buttons**.
- Settings are saved/loaded through the **Settings tab**.
- Batch runs automatically write a `senoquant_settings.json` file into the
  batch output root.

## Bundle envelope

All persisted settings use a top-level envelope:

```json
{
  "schema": "senoquant.settings",
  "version": 1,
  "batch_job": {},
  "tab_settings": {},
  "feature_settings": {},
  "segmentation_runs": []
}
```

For batch settings, `batch_job` is the key payload and other sections may be
empty.

Canonical JSON Schema for this envelope is stored at
`src/senoquant/utils/settings_bundle.schema.json`.

## `batch_job` payload schema

`batch_job` maps directly to `BatchJobConfig` in
`src/senoquant/tabs/batch/config.py`.

```json
{
  "input_path": "/path/to/images",
  "output_path": "/path/to/output",
  "extensions": [".tif", ".ome.tif"],
  "include_subfolders": false,
  "process_all_scenes": false,
  "overwrite": false,
  "channel_map": [
    {"name": "DAPI", "index": 0},
    {"name": "FITC", "index": 1}
  ],
  "nuclear": {
    "enabled": true,
    "model": "default_2d",
    "channel": "DAPI",
    "settings": {}
  },
  "cytoplasmic": {
    "enabled": false,
    "model": "cpsam",
    "channel": "FITC",
    "nuclear_channel": "DAPI",
    "settings": {}
  },
  "spots": {
    "enabled": false,
    "detector": "ufish",
    "channels": ["FITC"],
    "settings": {},
    "min_size": 0,
    "max_size": 0
  },
  "quantification": {
    "enabled": true,
    "format": "xlsx",
    "features": []
  }
}
```

`spots.min_size` and `spots.max_size` are legacy field names kept for
compatibility, but are interpreted as diameter thresholds in pixels when
filtering labels (2D effective area, 3D effective volume).

## Where persistence happens

### Settings tab save/load

- Save builds a bundle with:
  - `tab_settings` section for segmentation/spots tab state.
  - `batch_job` section from current Batch tab config.
- Load applies:
  - Segmentation and spots UI state from `tab_settings`.
  - Batch tab state from `batch_job` when present.

### Batch run output

`BatchBackend.process_folder()` writes `output_root/senoquant_settings.json`
before per-file processing begins. This captures the effective run config with
outputs.

### Programmatic API

`BatchJobConfig.save()` and `BatchJobConfig.load()` still exist for scripted
use and compatibility; they read/write the same bundle envelope.

## Legacy compatibility

`parse_settings_bundle()` accepts both:

- Legacy plain batch payloads (without the envelope), wrapped into `batch_job`.
- Legacy envelope payloads that stored settings under `feature`; these are
  mapped to `tab_settings` when `feature.kind == "tab_settings"`, otherwise
  to `feature_settings`.

This preserves backward compatibility for older JSON files.

## Developer checklist for batch config changes

When adding fields to batch configuration:

1. Update `BatchJobConfig` dataclasses in `src/senoquant/tabs/batch/config.py`.
2. Update serialization in `to_dict()` / `from_dict()`.
3. Update fallback derivation in
   `src/senoquant/tabs/batch/backend.py::_derive_batch_job_payload`.
4. Update settings-tab integration expectations if needed.
5. Add/adjust tests:
   - `tests/senoquant/tabs/batch/test_config.py`
   - `tests/senoquant/tabs/batch/test_batch_backend.py`
   - `tests/senoquant/tabs/settings/test_frontend.py`
