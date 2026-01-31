# Quick Start

This guide walks through the basic workflow for analyzing senescence markers in tissue images using SenoQuant.

## Prerequisites

- napari installed with SenoQuant.
- Multi-channel microscopy image (supported formats: `.tif`, `.czi`, `.lif`, `.nd2`, etc.).
- Channels containing: Nuclei, IF markers, and/or spots.

## Basic workflow

### 1. Launch napari and load image

In your terminal, activate the conda environment where SenoQuant is installed and start napari:

```bash
conda activate senoquant
napari
```

**Load your image:**
- `File` → `Open File(s)...` → Select your image.
- Or drag-and-drop the file into the napari window.

**Expected result:** Each channel appears as a separate layer in the layer list.

### 2. Open SenoQuant

`Plugins` → `SenoQuant`

The plugin window opens as a docked widget with 5 tabs:
- **Segmentation**
- **Spots**
- **Quantification**
- **Batch**
- **Settings**

### 3. Run nuclear segmentation

1. Switch to the **Segmentation** tab.
2. In the Nuclear segmentation box, select **Nuclear layer**: Choose the DAPI or nuclear stain channel.
3. Select **Model**: `default_2d` (for 2D images) or `default_3d` (for Z-stacks). `cpsam` is also available for nuclear+cytoplasmic segmentation.
4. Adjust model settings if needed (e.g., `Object diameter (px)`).

   > To quickly measure object diameter, create a napari shapes layer (left toolbar, new shapes layer icon) and draw a line across a representative nucleus. Then click `Layers` → `Measure` → `Toggle shapes dimensions measurement (napari builtins)` to see the length. See <https://napari.org/stable/howtos/layers/shapes.html> for more details.

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
3. Select **Detector**: `udwt` or `rmp`.
4. Adjust detection settings (e.g., `Product threshold(ld)`).

   > The default settings work well for most images.

5. (Optional) Set **Minimum size** and **Maximum size** to further filter spots.
6. Click **Run**.

**Output:** A labels layer named `<channel>_<detector>_spot_labels`.

### 6. Configure quantification features

The quantification tab organizes exports by **Features**. A feature defines *what* to quantify and *how*. In the current version, two feature types are supported: **Markers** and **Spots**. This is based on common data types in senescence research:

- **Markers**: Measure intensity-based markers (e.g., IF markers) within nuclear/cytoplasmic masks.
- **Spots**: Count spots and analyze colocalization within cell masks.

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
   - For each channel, name the channel (e.g., `DAPI`, `p16`), and select the image layer containing the marker. Optionally, click the **Set threshold** checkbox to define a intensity threshold for positive/negative calls automatically or manually. The threshold sliders are linked to the napari layer contrast limits for easy visualization.
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

**Under construction**

## Next steps

- [Segmentation](segmentation.md) - Detailed model settings and parameters
- [Spots](spots.md) - Advanced spot detection configuration
- [Quantification](quantification.md) - Feature export details and column definitions
- [Batch](batch.md) - Batch processing profiles and automation
- [Data](data.md) - Supported file formats and metadata handling
