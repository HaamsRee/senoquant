# Quick Start

This guide walks through the basic workflow for analyzing senescence markers in tissue images using SenoQuant.

## Prerequisites

- napari installed with SenoQuant plugin
- Multi-channel microscopy image (supported formats: `.tif`, `.czi`, `.lif`, `.nd2`, etc.)
- Channels containing: nuclei, cytoplasm markers, and/or senescence spots

## Basic Workflow

### 1. Launch napari and Load Image

```bash
napari
```

**Load your image:**
- `File` → `Open File(s)...` → Select your image
- Or drag-and-drop the file into the napari window

**Expected result:** Each channel appears as a separate layer in the layer list.

### 2. Open SenoQuant Plugin

`Plugins` → `SenoQuant`

The plugin window opens as a docked widget with 5 tabs:
- **Segmentation**
- **Spots**
- **Quantification**
- **Batch**
- **Settings**

### 3. Run Nuclear Segmentation

1. Switch to the **Segmentation** tab
2. Select **Task**: `Nuclear`
3. Select **Image Layer**: Choose the DAPI or nuclear stain channel
4. Select **Model**: `default_2d` (for 2D images) or `default_3d` (for Z-stacks)
5. Adjust model settings if needed (e.g., `Object diameter (px)`)
6. Click **Run Segmentation**

**Output:** A new labels layer named `<channel>_<model>_nuc_labels` appears in the layer list.

### 4. (Optional) Run Cytoplasmic Segmentation

If you need to define cell boundaries:

1. Keep **Task** as `Nuclear` or switch to `Cytoplasmic`
2. For cytoplasmic models:
   - Select **Model**: `nuclear_dilation` or `perinuclear_rings`
   - Select **Image Layer**: Nuclear mask (for morphological models)
   - Adjust **Dilation/Erosion Distance** parameters
3. Click **Run Segmentation**

**Output:** A new labels layer named `<channel>_<model>_cyto_labels`.

### 5. (Optional) Detect Senescence Spots

If your image contains punctate senescence markers (e.g., senescence-associated β-galactosidase foci):

1. Switch to the **Spots** tab
2. Select **Image Layer**: Choose the channel with spots
3. Select **Detector**: `udwt` or `rmp`
4. Adjust detection settings (e.g., `Threshold`)
5. (Optional) Set **Min Size** and **Max Size** to filter spots by area
6. Click **Run Detection**

**Output:** A labels layer named `<channel>_<detector>_spot_labels`.

### 6. Configure Quantification Features

1. Switch to the **Quantification** tab
2. Click **Add Feature** → Select feature type:
   - **Markers**: For intensity-based marker quantification
   - **Spots**: For spot counting and colocalization

#### Configure Markers Feature

1. Click **Add Segmentation** → Select nuclear or cytoplasmic mask
2. Click **Add Channel** → Select intensity channel(s) to measure
3. (Optional) Click **Add ROI** → Draw ROI on image to restrict analysis
4. Click **Save Feature**

#### Configure Spots Feature

1. Click **Add Segmentation** → Select mask for cell boundary definition
2. Click **Add Channel** → Select spot labels layer(s)
3. (Optional) Enable **Export Colocalization** for multi-channel spot analysis
4. (Optional) Click **Add ROI** → Restrict to specific region
5. Click **Save Feature**

### 7. Export Quantification Data

1. In the **Quantification** tab, ensure all features are configured
2. Choose **Export Format**: `CSV` or `XLSX` (Excel)
3. Click **Export**
4. Select output directory

**Output:** Excel/CSV files containing:
- **Markers**: Mean/median/std intensity per cell, morphology metrics
- **Spots**: Spot counts per cell, spot densities, colocalization data (if enabled)

## Output Layer Naming

SenoQuant uses predictable naming conventions for generated layers:

| Output Type | Layer Name Format | Example |
| --- | --- | --- |
| Nuclear Mask | `<image>_<model>_nuc_labels` | `DAPI_default_2d_nuc_labels` |
| Cytoplasmic Mask | `<image>_<model>_cyto_labels` | `CellMask_nuclear_dilation_cyto_labels` |
| Spot Labels | `<image>_<detector>_spot_labels` | `SA-bGal_udwt_spot_labels` |
| Colocalization | `<labels_A>_<labels_B>_colocalization` | `CH1_spots_CH2_spots_colocalization` |

**Note:** Rerunning segmentation or spot detection with the same parameters replaces existing layers.

## Batch Processing Workflow

For high-throughput analysis of multiple images:

1. Switch to the **Batch** tab
2. **Input Folder**: Select folder containing images
3. **Output Folder**: Select destination for results
4. Configure channel mapping (assign names to channel indices)
5. Enable and configure:
   - **Nuclear Segmentation**
   - **Cytoplasmic Segmentation**
   - **Spot Detection**
   - **Quantification** (copy settings from Quantification tab)
6. Click **Run Batch**

**Output:** Folder structure with masks and quantification spreadsheets for each image.

## Tips for Best Results

- **Segmentation Quality**: Adjust `Object diameter (px)` to match your nuclear/cell size
- **Spot Detection Sensitivity**: Start with default `Threshold` values; increase to reduce false positives
- **ROI Usage**: Use ROIs to exclude edge artifacts or focus on specific tissue regions
- **Multi-Scene Files**: Batch processing can optionally process all scenes; check `Process All Scenes`
- **Model Selection**: Use `default_2d` for single Z-planes, `default_3d` for Z-stacks, `cpsam` for advanced nuclear+cytoplasmic segmentation

## Next Steps

- [Segmentation](segmentation.md) - Detailed model settings and parameters
- [Spots](spots.md) - Advanced spot detection configuration
- [Quantification](quantification.md) - Feature export details and column definitions
- [Batch](batch.md) - Batch processing profiles and automation
- [Data](data.md) - Supported file formats and metadata handling
