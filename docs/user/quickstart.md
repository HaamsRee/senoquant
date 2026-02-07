# Quick Start

This guide walks through the basic workflow for analyzing senescence markers in tissue images using SenoQuant.

## Prerequisites

- napari installed with SenoQuant.
- System meets the [installation requirements](installation.md#system-requirements).
- Multi-channel microscopy image (supported formats: `.tif`, `.czi`, `.lif`, `.nd2`, etc.).
- Channels containing: Nuclei, IF markers, and/or spots.

## Basic workflow

### 1. Launch napari and load image

**If you used the Installer:**

- Launch **SenoQuant** from the Start Menu or the desktop icon.

**Manual installs (conda/uv):**

In your terminal, activate the conda environment where SenoQuant is installed and start napari:

```bash
conda activate senoquant
napari --with senoquant
```

**Load your image:**

- `File` → `Open File(s)...` → Select your image.

    > A popup may appear for you to select the appropriate reader plugin. Choose `senoquant`.

- Or drag-and-drop the file into the napari window.

**Expected result:** Each channel appears as a separate layer in the layer list. If you're opening a multi-scene file, select the desired scene(s) from the popup.

### 2. Open SenoQuant

SenoQuant should launch automatically in Step 1. If not:

`Plugins` → `SenoQuant`

The plugin window opens as a docked widget with 6 tabs:

- **Segmentation**
- **Spots**
- **Quantification**
- **Visualization**
- **Batch**
- **Settings**

### 3. Run nuclear segmentation

1. Switch to the **Segmentation** tab.
2. In the Nuclear segmentation box, select **Nuclear layer**: Choose the DAPI or nuclear stain channel.
3. Select **Model**: `default_2d` (for 2D images) or `default_3d` (for Z-stacks). `cpsam` is also available for nuclear+cytoplasmic segmentation.
4. Adjust model settings if needed (e.g., `Object diameter (px)`).

    > To quickly estimate object diameter, create a napari Shapes layer, draw a line across a representative nucleus, then use `Layers` → `Measure` → `Toggle shapes dimensions measurement (napari builtins)`. See <https://napari.org/stable/howtos/layers/shapes.html> for details.

    > The default settings work well for most images.

5. Click **Run**.

**Output:** A new labels layer named `<channel>_<model>_nuc_labels` appears in the layer list.

### 4. (Optional) Run cytoplasmic segmentation

If you need to catch cytoplasmic regions for marker quantification:

1. In the **Segmentation** tab, go to the Cytoplasmic segmentation box.
2. Select **Model**: `cpsam`, `nuclear_dilation` or `perinuclear_rings`.
3. Select image/labels layers.
4. Adjust model settings if needed.
5. Click **Run**.

**Output:** A new labels layer named `<channel>_<model>_cyto_labels`.

### 5. (Optional) Detect spots

If your image contains punctate spots (e.g., gH2AX, telomeres, FISH spots):

1. Switch to the **Spots** tab.
2. Select **Image Layer**: Choose the channel with spots.
3. Select **Detector**: `rmp`, `ufish`.
4. Adjust detection settings (for example, `Threshold`).

    > The default settings work well for most images.

5. (Optional) Set **Minimum diameter** and **Maximum diameter** to filter detected spots.
6. Click **Run**.

**Output:** A labels layer named `<channel>_<detector>_spot_labels`.

### 6. Configure quantification features

The quantification tab organizes exports by **Features**. A feature defines *what* to quantify and *how*. In the current version, two feature types are supported: **Markers** and **Spots**. This is based on common data types in senescence research:

- **Markers**: Measure intensity-based markers (e.g., IF markers) within nuclear/cytoplasmic masks.
- **Spots**: Count spots and analyze colocalization within cell masks.

To add a feature:

1. Switch to the **Quantification** tab.
2. Click **Add feature** → Select feature **Type**:

    - **Markers**: For intensity-based IF marker quantification.
    - **Spots**: For spot counting and colocalization.

3. Name your feature (e.g., `IF markers`, `IF spots`).

#### Configure a Markers feature

1. Click **Add channels**.
2. In the popup:

    - In the top **Segmentations** box, click **Add segmentation** → Add nuclear/cytoplasmic labels layer.
    
        > The selected segmentation defines the nuclei/cells for quantification. SenoQuant will export one cell x marker table per segmentation.

    - In the **Channels** box, click **Add channel** → Add intensity channel(s) to quantify.
    - For each channel, name the channel (e.g., `DAPI`, `p16`), and select the image layer containing the marker. Optionally, click the **Set threshold** checkbox to define an intensity threshold for positive/negative calls automatically or manually. The threshold sliders are linked to the napari layer contrast limits for easy visualization.
    - Click **Save** or close the popup when done.

3. (Optional) Draw ROIs with a shapes layer. Enable **ROIs** → Name the ROI → Select the shapes layer. Select the ROI **Type** to be `Include` or `Exclude`. Nuclei/cells inside `Include` ROIs or outside `Exclude` ROIs will be marked in the output table.

#### Configure a Spots feature

1. Click **Add channels**.
2. In the popup:

    - In the top box, click **Add segmentation** → Add nuclear/cytoplasmic labels layer to exclude spots outside these segmented cells.
    
        > The selected segmentation defines the nuclei/cells for spot quantification. SenoQuant will export one set of spots tables per segmentation.

    - In the **Channels** box, click **Add channel** → Add spot channel(s) to quantify.
    - For each channel, name the channel (e.g., `gH2AX`, `Telomere`), and select the spot labels layer in **Channel**. Select the corresponding **Spots segmentation** layer generated in the **Spots** tab.
    - Click **Save** or close the popup when done.

3. (Optional) Enable **ROIs** → Name the ROI → Select the shapes layer. ROIs work the same way as in the Markers feature.
4. (Optional) Enable **Export colocalization** to analyze spot colocalization between two or more spot channels. Colocalization will only be computed if two or more spot channels are added to the feature.

### 7. Run quantification

1. In the **Quantification** tab, ensure all features are configured
2. In the **Output** box, browse to select an output folder.
3. Name the quantification run in **Save name**.
4. Choose **Format**: `xlsx` (Excel) or `csv`.
5. Click **Process**.
6. Wait for quantification to complete.

**Output:** Excel/CSV files containing:

- **Markers**: Marker intensities per cell, morphological features.
- **Spots**: Spot counts per cell, spot intensities, colocalization data (if enabled).

## Batch processing workflow

For high-throughput analysis of multiple images:

### 1. Open the Batch tab

In the SenoQuant dock widget, select **Batch**.

### 2. Configure inputs

1. **Input folder** → Choose the directory containing images.
2. **Extensions** → List the file types to include (e.g., `.tif, .nd2, .czi`).
3. (Optional) **Include subfolders** → Enable if your data are nested.
4. (Optional) **Process all scenes** → Enable for multi-scene files.

### 3. Map channels

Add channel names and indices so they appear in all dropdowns:

- **Name**: `DAPI`, `FITC`, `Cy3`, etc.
- **Index**: zero-based channel index

### 4. Enable processing steps

Configure only the steps you need:

- **Nuclear segmentation** → Enable, select model and channel, adjust settings.
- **Cytoplasmic segmentation** (optional) → Enable if needed.
- **Spot detection** (optional) → Choose detector and channels; set min/max diameter-style filtering if needed.

### 5. Configure quantification (optional)

If you want batch exports:

1. Enable **Quantification**.
2. Click **Add feature** and set up **Markers** or **Spots** features as in the single-image workflow.

> Note: ROI selection and threshold tuning are not available in batch mode.

### 6. Set outputs and run

1. **Output folder** → Choose where results are written.
2. (Optional) **Overwrite** → Enable to replace existing outputs.
3. Click **Run batch**.

**Outputs:** Each input image gets its own output folder with (if enabled)
quantification tables plus per-feature `feature_settings.json` metadata files.
Masks are also saved. The batch output root includes a `senoquant_settings.json`
file with the batch configuration used for the run.

## Settings persistence (recommended)

Before closing napari, save your configuration:

1. Open the **Settings** tab.
2. Click **Save settings** and store `senoquant_settings.json`.

To continue later, click **Load settings** in the same tab.
If the JSON contains batch configuration, the Batch tab is populated too.

## Next steps

- [Segmentation](segmentation.md) - Detailed model settings and parameters
- [Spots](spots.md) - Advanced spot detection configuration
- [Quantification](quantification.md) - Feature export details and column definitions
- [Visualization](visualization.md) - Plot generation from quantification tables
- [Batch](batch.md) - Batch processing and automation
- [Data](data.md) - Supported file formats and metadata handling
