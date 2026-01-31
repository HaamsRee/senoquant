# Batch Processing

The Batch tab automates segmentation, spot detection, and quantification across entire folders of images.

## Interface Overview

### Input Section

**Controls:**

- **Input folder** (browse button): Select folder containing images
- **Extensions** (text field): Comma-separated file extensions (e.g., `.tif, .nd2, .czi`)
- **Include subfolders** (checkbox): Recursively process nested folders
- **Process all scenes** (checkbox): Process every scene in multi-scene files (unchecked = first scene only)

### Channel Mapping

Define channel names for easier configuration throughout the batch setup.

**Table Columns:**
- **Name**: User-friendly channel name (e.g., "DAPI", "FITC")
- **Index**: Zero-based channel number in images
- **+ button**: Add a new channel mapping
- **× button** (per row): Remove this channel mapping

**Usage:** Channel names appear in all dropdowns below (segmentation, spots), making configuration more intuitive.

### Nuclear Segmentation

**Controls:**

- **Enable** (checkbox): Turn on/off nuclear segmentation
- **Model** (dropdown): Select nuclear segmentation model
- **Channel** (dropdown): Select channel (uses names from channel map if defined, or indices)
- **Settings** (button): Opens dialog to configure model parameters

### Cytoplasmic Segmentation

**Controls:**

- **Enable** (checkbox): Turn on/off cytoplasmic segmentation
- **Model** (dropdown): Select cytoplasmic segmentation model
- **Channel** (dropdown): Select cytoplasm channel
- **Nuclear channel** (dropdown): Select nuclear channel (required for some models like `nuclear_dilation`, `perinuclear_rings`)
- **Settings** (button): Opens dialog to configure model parameters

### Spot Detection

**Controls:**

- **Enable** (checkbox): Turn on/off spot detection
- **Detector** (dropdown): Select spot detection algorithm
- **Channels** (multi-select list): Select one or more channels for spot detection
- **Min size** (spin box): Minimum spot size filter in pixels (0 = disabled)
- **Max size** (spin box): Maximum spot size filter in pixels (0 = disabled)
- **Settings** (button): Opens dialog to configure detector parameters

### Quantification

Embedded quantification feature configuration (simplified version of Quantification tab):

**Controls:**

- **Enable** (checkbox): Turn on/off quantification
- **Add feature** (button): Opens dialog to configure a quantification feature
- **Feature list**: Shows configured features
- **Format** (dropdown): Choose `csv` or `xlsx` for quantification exports

**Note:** ROI controls and threshold configuration are disabled in batch mode. Thresholds must be pre-configured in the feature settings.

### Output Section

**Controls:**

- **Output folder** (browse button): Select destination folder for results
- **Format** (dropdown): Mask output format - `tif` (TIFF) or `npy` (NumPy array)
- **Overwrite** (checkbox): Overwrite existing outputs (unchecked = skip existing folders)

### Profiles

**Controls:**

- **Save profile** (button): Save current batch configuration to JSON file
- **Load profile** (button): Load batch configuration from JSON file

**Use case:** Save commonly used configurations for repeat analyses.

### Execution

**Controls:**

- **Run batch** (button): Start batch processing
- **Progress bar**: Shows completion percentage
- **Status label**: Displays current file being processed

**During execution:**
- Progress bar updates in real-time
- Status shows: "Processing {filename}..." or "Processing {filename} (Scene: {scene_id})..."
- UI remains responsive (processing runs in background thread)

## Output Structure

Batch creates organized output folders:

```
output_folder/
  image_name_1/
    {channel}_{model}_nuc_labels.tif
    {channel}_{model}_cyto_labels.tif
    {channel}_{detector}_spot_labels.tif
    Feature_Name/
      segmentation_1.xlsx
      segmentation_2_cells.xlsx
      segmentation_2_spots.xlsx
  image_name_2/
    ...
```

For multi-scene files with "Process all scenes" enabled:

```
output_folder/
  image_name/
    Scene_0/
      {channel}_{model}_nuc_labels.tif
      ...
    Scene_1/
      {channel}_{model}_nuc_labels.tif
      ...
```

### File Naming Conventions

**Segmentation masks:**
- Nuclear: `{channel}_{model}_nuc_labels.{format}`
- Cytoplasmic: `{channel}_{model}_cyto_labels.{format}`

**Spot masks:**
- `{channel}_{detector}_spot_labels.{format}`

**Quantification:**
- Markers: `{segmentation_label}.{format}`
- Spots: `{segmentation_label}_cells.{format}` and `{segmentation_label}_spots.{format}`

**Example:**
- `DAPI_default_2d_nuc_labels.tif` - Nuclear segmentation on DAPI channel with default_2d model
- `FITC_udwt_spot_labels.tif` - Spot detection on FITC channel with udwt detector

## Tips & Best Practices

**Extension filtering:**
- Use exact extensions including the dot: `.tif` not `tif`
- Multiple extensions: `.tif, .tiff, .nd2, .czi`
- Extensions are normalized (case-insensitive, dots added automatically if missing)

**Channel mapping:**
- Define meaningful names for easier configuration
- Indices are 0-based (first channel = 0)
- If no mapping defined, use numeric indices directly

**Multi-scene processing:**
- Enable to process all scenes separately
- Each scene gets its own subfolder
- Useful for multi-position experiments

**Overwrite behavior:**
- Unchecked: Skips folders that already exist (allows resuming interrupted batches)
- Checked: Replaces all contents in existing folders

**Performance:**
- Batch processes files sequentially (one at a time)
- Large images may require significant memory
- Consider breaking very large batches into smaller chunks

**Error handling:**
- Failed files don't stop the entire batch
- Check progress messages for file-specific errors
- Successful outputs are still saved even if some files fail

## Workflow Example

1. **Prepare:**
   - Open napari and load one test image
   - Test segmentation/spot detection parameters interactively
   - Note optimal settings

2. **Configure Batch:**
   - Set input folder and extensions
   - Add channel mappings
   - Enable and configure nuclear/cytoplasmic segmentation
   - Enable and configure spot detection
   - Add quantification features
   - Set output folder

3. **Save Profile:**
   - Click "Save profile"
   - Name it descriptively (e.g., "p21_senescence_analysis.json")

4. **Run:**
   - Click "Run batch"
   - Monitor progress bar
   - Check status messages for any errors

5. **Reuse:**
   - For future analyses, click "Load profile"
   - Select your saved JSON file
   - Adjust input/output paths as needed
   - Run again
