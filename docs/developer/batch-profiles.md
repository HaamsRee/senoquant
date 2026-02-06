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
  "feature": {},
  "segmentation_runs": []
}
```

For batch settings, `batch_job` is the key payload and other sections may be
empty.

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
  "output_format": "tif",
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

## Where persistence happens

### Settings tab save/load

- Save builds a bundle with:
  - `feature` section for segmentation/spots tab state.
  - `batch_job` section from current Batch tab config.
- Load applies:
  - Segmentation and spots UI state from `feature`.
  - Batch tab state from `batch_job` when present.

### Batch run output

`BatchBackend.process_folder()` writes `output_root/senoquant_settings.json`
before per-file processing begins. This captures the effective run config with
outputs.

### Programmatic API

`BatchJobConfig.save()` and `BatchJobConfig.load()` still exist for scripted
use and compatibility; they read/write the same bundle envelope.

## Legacy compatibility

`parse_settings_bundle()` accepts legacy plain batch payloads (without the
envelope) and wraps them into `batch_job`.

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
