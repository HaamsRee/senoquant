# Settings

The Settings tab is the central place for persisting and reloading
analysis configuration across tabs.

It uses a unified JSON bundle (`senoquant_settings.json`) so the same file
format can be reused by:

- Manual save/load from the Settings tab.
- Batch output metadata generated after batch runs.
- Quantification feature exports that include settings context.

## Controls

- **Save settings**: Writes a `senoquant_settings.json` file.
- **Load settings**: Reads a `senoquant_settings.json` file and applies
  supported settings.

## What is saved

### Segmentation tab state

- Selected nuclear model.
- Current nuclear model settings.
- Selected cytoplasmic model.
- Current cytoplasmic model settings.

### Spots tab state

- Selected detector.
- Current detector settings.
- Spot size filters (minimum and maximum size).

### Batch tab state

- Current batch configuration is saved into the bundle under `batch_job`.
- This allows the same file to restore batch UI state later.

## What is restored on load

- Segmentation model selections and settings.
- Spots detector settings and size filters.
- Batch tab state, when the loaded JSON contains a non-empty `batch_job`
  section.

## What is not restored

- Quantification tab feature configuration.
- Visualization tab plot configuration.
- Runtime viewer state (active layer selection, visibility, colormaps).

## Typical workflow

1. Configure Segmentation and Spots parameters in their tabs.
2. Optionally configure Batch settings.
3. Open **Settings** and click **Save settings**.
4. Reopen later and click **Load settings** to restore the saved setup.

## Notes

- The UI stores and restores settings by key, so unknown keys in a JSON file
  are ignored safely.
- If a model or detector from the file is unavailable in the current
  installation, that specific selection cannot be applied.
