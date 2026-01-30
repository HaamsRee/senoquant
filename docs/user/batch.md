# Batch Processing

The Batch tab runs segmentation, spot detection, and quantification over
folders of images.

## Running Batch Jobs

When you click "Run batch", the processing will execute in the background.
A progress bar displays the current progress, showing:

- The percentage of completion
- Current item being processed
- Status messages for each file/scene

The progress bar and status label update in real-time as the batch job
progresses.

## Input

- **Input folder**: folder containing images.
- **Extensions**: comma-separated list of file extensions to include.
- **Include subfolders**: recurse into nested folders.
- **Process all scenes**: process every scene in multi-scene files.
- **Profiles**: save/load batch configurations as JSON.

## Channels

Define a channel map (name + index). These names are used throughout the
batch configuration (segmentation channel picks, spot channels, etc.).

## Segmentation

- Enable nuclear and/or cytoplasmic segmentation.
- Select a model and channel for each task.
- Edit model settings via the settings dialog.

## Spots

- Enable spot detection.
- Select a detector and one or more channels.
- Edit detector settings via the settings dialog.

## Quantification

Batch quantification embeds a simplified Quantification UI:

- Feature list is available.
- ROI controls and thresholds are disabled in batch mode.
- Output format is selected in the Output section.

## Output

- Output folder and format (`tif` or `npy`).
- Quantification export format (`xlsx` or `csv`).
- Overwrite toggle for existing outputs.

### Output naming

Batch writes outputs with standard names:

- `<channel>_<model>_nuc_labels` for nuclear segmentation.
- `<channel>_<model>_cyto_labels` for cytoplasmic segmentation.
- `<channel>_<detector>_spot_labels` for each spot channel.

When `tif` output fails, batch falls back to `.npy` automatically.
