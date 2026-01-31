# Quantification

The Quantification tab extracts measurements from segmented images and exports them to spreadsheet files.

## Interface Overview

### Top Controls

- **Add feature** (button): Opens a dialog to create a new quantification feature
- **Feature list** (panel): Shows all configured features with name, type, and delete button
- **Output path** (browse field): Select folder where results will be saved
- **Output name** (text field): Name for the output subfolder (optional)
- **Format** (dropdown): Choose `csv` or `xlsx` for export format
- **Process** (button): Execute quantification and export results

### Feature Configuration Dialog

When you click **Add feature**, a dialog opens to configure the feature:

**Common Controls:**
- **Feature name** (text field): Custom name for this feature
- **Feature type** (dropdown): Select "Markers" or "Spots"
- **Add** (button): Save feature to the list
- **Cancel** (button): Discard and close dialog

## Feature Types

### Markers Feature

Measures channel intensity and morphological properties within segmentation labels.

**Configuration Controls:**

**Segmentation Section:**
- **+ button**: Add a segmentation layer
- **Label** (dropdown per row): Select a labels layer (nuclear or cytoplasmic masks)
- **Task** (dropdown per row): Specify "nuclear" or "cytoplasmic" for reference columns
- **× button** (per row): Remove this segmentation

**Channels Section:**
- **+ button**: Add an image channel
- **Channel** (dropdown per row): Select an image layer to measure
- **Threshold** (checkbox per row): Enable intensity thresholding
  - **Threshold value** (spin box): Threshold level (enabled when checkbox checked)
  - **Mode** (dropdown): "absolute" (direct intensity) or "percentile" (percentage-based)
- **× button** (per row): Remove this channel

**ROI Section:**
- **+ button**: Add a region of interest filter
- **Layer** (dropdown per row): Select a Shapes layer
- **Mode** (dropdown per row): "include" (keep only overlapping) or "exclude" (remove overlapping)
- **× button** (per row): Remove this ROI

#### Exported Columns (Markers)

**Morphological Metrics (2D images):**
- `morph_area` - Area in pixels
- `morph_area_um2` - Area in µm² (if pixel sizes available)
- `morph_perimeter` - Perimeter in pixels
- `morph_perimeter_crofton` - Crofton perimeter estimate
- `morph_circularity` - 4π·area/perimeter² (1.0 = perfect circle)
- `morph_eccentricity` - 0 (circular) to 1 (elongated)
- `morph_solidity` - area / convex hull area
- `morph_extent` - area / bounding box area
- `morph_feret_diameter_max` - Maximum Feret diameter
- `morph_major_axis_length` - Major axis of fitted ellipse
- `morph_minor_axis_length` - Minor axis of fitted ellipse
- `morph_aspect_ratio` - major axis / minor axis
- `morph_orientation` - Angle in radians

**Morphological Metrics (3D images):**
- `morph_volume` - Volume in pixels
- `morph_volume_um3` - Volume in µm³ (if pixel sizes available)
- Limited shape descriptors (regionprops 3D limitation)

**Centroid Coordinates:**
- 2D: `centroid_row`, `centroid_col` (pixels and µm if available)
- 3D: `centroid_plane`, `centroid_row`, `centroid_col` (pixels and µm if available)

**Intensity Metrics (per channel):**
- `{channel}_mean_intensity` - Mean pixel intensity
- `{channel}_integrated_intensity` - mean × area × pixel_volume
- `{channel}_raw_integrated_intensity` - Sum of pixel values

**Thresholded Intensity (when enabled):**
- `{channel}_mean_intensity_thresholded`
- `{channel}_integrated_intensity_thresholded`
- `{channel}_raw_integrated_intensity_thresholded`

**Reference Columns:**
- `file_name` - Source image filename
- `file_path` - Full source path
- `segmentation_type` - "nuclear" or "cytoplasmic"
- `segmentation_label` - Label layer name
- `nuclear_label` - (cytoplasmic only) Associated nuclear label ID

**ROI Columns:**
- `roi_included` - Boolean, passed include filters
- `roi_excluded` - Boolean, was excluded
- `roi_include_names` - Comma-separated including ROI names
- `roi_exclude_names` - Comma-separated excluding ROI names

### Spots Feature

Measures spot counts, density, and properties within cells.

**Configuration Controls:**

**Segmentation Section:**
- **+ button**: Add a cell segmentation layer
- **Label** (dropdown per row): Select a labels layer for cell boundaries
- **× button** (per row): Remove this segmentation

**Channels Section:**
- **+ button**: Add a spot channel
- **Image channel** (dropdown per row): Select the image layer
- **Spots labels** (dropdown per row): Select the spot labels layer
- **× button** (per row): Remove this channel

**ROI Section:** (same as Markers)

**Colocalization:**
- **Export colocalization** (checkbox): Include colocalization analysis in output

#### Exported Tables (Spots)

**Cells Table** (one per segmentation):
- All morphological metrics (same as Markers)
- All centroid metrics (same as Markers)
- ROI columns (same as Markers)
- `{channel}_spot_count` - Number of spots in this cell
- `{channel}_spot_density` - spots / area (2D) or spots / volume (3D)
- `{channel}_mean_spot_intensity` - Mean intensity of spots
- Colocalization columns (when enabled):
  - `{channelA}_{channelB}_coloc_count`
  - `{channelA}_{channelB}_coloc_ratio`

**Spots Table** (one per segmentation):
- `spot_id` - Unique identifier within channel
- `channel` - Source channel name
- `cell_label` - Parent cell ID (0 if unassigned)
- `centroid_*` - Spot coordinates (pixels and µm)
- `morph_area` / `morph_volume` - Spot size
- `mean_intensity` - Mean intensity of spot region
- ROI columns (inherited from parent cell)

## Output Structure

Results are saved to: `{output_path}/{output_name}/{feature_name}/`

Each feature creates its own subfolder containing:
- One file per segmentation (Markers)
- Two files per segmentation: `*_cells` and `*_spots` (Spots)
- `marker_thresholds.json` (Markers with thresholds enabled)

**File naming:**
- Markers: `{segmentation_label}.{format}`
- Spots: `{segmentation_label}_cells.{format}` and `{segmentation_label}_spots.{format}`

## Tips

**ROI Usage:**
- Use "include" mode to analyze only specific regions
- Use "exclude" mode to remove artifacts or edges
- Multiple ROIs can be combined in the same feature

**Thresholds:**
- "absolute" mode: Direct intensity value (e.g., 100)
- "percentile" mode: Percentage of intensity range (e.g., 50 = median)

**Colocalization:**
- Requires at least 2 spot channels
- Computes pairwise adjacency between spot types
- Adds columns to cells table and spots table
