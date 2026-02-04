# Batch profiles

Batch profiles are JSON files representing `BatchJobConfig`. They can be
saved and loaded from the Batch tab.

## Top-level schema

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
    "model": "stardist_2d",
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
    "settings": {}
  },
  "quantification": {
    "enabled": true,
    "format": "xlsx",
    "features": []
  }
}
```

Notes:

- `extensions` is normalized in the backend (dots added, lowercased).
- `channel_map` drives channel pickers in the Batch UI.
- Segmentation and spot settings are stored as dictionaries keyed by
  `details.json` setting keys.
- `quantification.features` uses the same serialized structure as the
  Quantification tab.
