# Quantification

The Quantification tab extracts measurements from segmented images and exports them to spreadsheet files.

## Interface overview

### Main interface controls

- **Add feature** (button): Create a new quantification feature.
- **Features list** (panel): Shows all configured features with name, type, and delete button.
- **Output folder** (browse field): Select folder where results will be saved.
- **Save name** (text field): Name for the output subfolder (optional).
- **Format** (dropdown): Choose `xlsx` or `csv` for export format.
- **Process and save** (button): Execute quantification and save results.

### Feature configuration dialog

When you click **Add feature**, a numbered feature appears in the Features list:

**Common fields:**

- **Name**: Custom name for this feature (e.g., `IF markers`, `IF spots`).
- **Feature type** (dropdown): Select "Markers" or "Spots".
- **Delete** (button): Remove this feature.

## Feature types

The quantification tab organizes exports by **Features**. A feature defines *what* to quantify and *how*. In the current version, two feature types are supported: **Markers** and **Spots**. This is based on common data types in senescence research:

- **Markers**: Measure intensity-based markers (e.g., IF markers) within nuclear/cytoplasmic masks.
- **Spots**: Count spots and analyze colocalization within cell masks.

### Markers feature

Measures channel intensity and morphological properties within segmentation labels.

<u>**Add channels popup:**</u>

**Segmentation section:**

- **Add segmentation**: Add a segmentation layer.
- **Labels** (dropdown per row): Select a labels layer (nuclear or cytoplasmic masks).
- **Delete** (per row): Remove this segmentation.

> Each segmentation added here will be applied to all channels in this feature. SenoQuant will export one cell x marker table per segmentation.

**Channels section:**

- **Add channel**: Add an image channel.
- **Channel** (dropdown per row): Select an image layer to measure intensities from.
- **Set threshold** (checkbox per row): Enable intensity thresholding.

    - **Threshold** (slider): Threshold level (enabled when checkbox checked). The values set here are linked to the napari layer contrast limits for easy visualization. **Mean** intensities outside and within the thresholded region will marked in the output files.
    - **Method** (dropdown): Various thresholding methods:

        - `Manual`: Set threshold using slider.
        - `Otsu`: Automatic Otsu thresholding.
        - `Yen`: Automatic Yen thresholding.
        - `Li`: Automatic Li thresholding.
        - `Isodata`: Automatic Isodata thresholding.
        - `Triangle`: Automatic Triangle thresholding.
        
        > Click the "Auto threshold" button to compute the threshold using the selected automatic method. For more details on these methods, refer to the [skimage documentation](https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_thresholding.html).

    - **Delete** (per row): Remove this channel.

> Closing the popup or clicking **Save** will save the settings.

<u>**ROI section:**</u>

> Enabled by checking the **ROIs** checkbox in the main feature configuration box.

- **Add ROI**: Add a region of interest filter.
- **Layer** (dropdown): Select a Shapes layer.
- **Type** (dropdown): "Include" (mark overlapping as 1 in output) or "Exclude" (mark overlapping as 0 in output).
- **Delete**: Remove this ROI.

#### Exported columns (Markers)

**Morphological metrics (2D images):**

- `morph_area` - Area in pixels.
- `morph_area_um2` - Area in µm² (if pixel sizes available).
- `morph_perimeter` - Perimeter in pixels.
- `morph_perimeter_crofton` - Crofton perimeter estimate.
- `morph_circularity` - 4π·area/perimeter² (1.0 = perfect circle).
- `morph_eccentricity` - 0 (circular) to 1 (elongated).
- `morph_solidity` - area / convex hull area.
- `morph_extent` - area / bounding box area.
- `morph_feret_diameter_max` - Maximum Feret diameter.
- `morph_major_axis_length` - Major axis of fitted ellipse.
- `morph_minor_axis_length` - Minor axis of fitted ellipse.
- `morph_aspect_ratio` - major axis / minor axis.
- `morph_orientation` - Angle in radians.

**Morphological metrics (3D images):**

- `morph_volume` - Volume in pixels.
- `morph_volume_um3` - Volume in µm³ (if pixel sizes available).
- Limited shape descriptors (regionprops 3D limitation).

**Centroid coordinates:**

- 2D: `centroid_y`, `centroid_x` (pixels and µm if available).
- 3D: `centroid_z`, `centroid_y`, `centroid_x` (pixels and µm if available).

**Intensity metrics (per channel):**

- `<channel>_mean_intensity` - Mean pixel intensity.
- `<channel>_integrated_intensity` - mean × area × pixel_volume.
- `<channel>_raw_integrated_intensity` - Sum of pixel values.

**Thresholded intensity (when enabled):**

- `<channel>_mean_intensity_thresholded`
- `<channel>_integrated_intensity_thresholded`
- `<channel>_raw_integrated_intensity_thresholded`

> Thresholding will zero the `_thresholded` fields of cells with **mean** intensities outside the thresholding bounds.

**Reference columns:**

- `label_id` - Unique ID of the segmentation instance (a nucleus or a cytoplasm).
- `file_path` - Full source path.
- `segmentation_type` - "nuclear" or "cytoplasmic".
- `overlaps_with` - Semicolon-separated list of overlapping labels from other segmentations in this feature, if there are multiple segmentations configured.

**ROI columns:**

- `excluded_from_roi_<name>` - 0/1 flag indicating if the cell is excluded by the named ROI.
- `included_in_roi_<name>` - 0/1 flag indicating if the cell is included by the named ROI.

### Spots feature

Measures spot counts and spot-level properties within selected cell segmentations.

<u>**Add channels popup:**</u>

**Segmentation section:**

- **Add segmentation**: Add a nuclear/cytoplasmic labels layer.
- **Segmentation** (dropdown per row): Select a cell segmentation layer.
- **Delete** (per row): Remove this segmentation.

> Each segmentation added here is used to exclude background spots. SenoQuant exports one pair of files (`*_cells` and `*_spots`) per segmentation.

**Channels section:**

- **Add channel**: Add a spot channel row.
- **Name** (text): Custom channel label for output columns and colocalization labels.
- **Channel** (dropdown per row): Select the image layer used for spot intensity.
- **Spots segmentation** (dropdown per row): Select the labels layer containing spot instances for this channel.
- **Delete** (per row): Remove this channel.

> A channel row is exported only when both **Channel** and **Spots segmentation** are selected.
>
> If a selected layer is missing at runtime, or the spots labels shape does not match the cell segmentation shape, that channel is skipped for that segmentation.
>
> Spot labels are assigned to cells by centroid position. Spots with centroids outside the selected cell segmentation are excluded.
>
> Closing the popup or clicking **Save** will save the settings.

<u>**ROI section:**</u>

> Enabled by checking the **ROIs** checkbox in the main feature configuration box.
>
> ROI controls are the same as in the Markers feature.

**Colocalization:**

- **Export colocalization** (checkbox): Include colocalization analysis in output.

> Colocalization is computed from overlap between spot label masks across channels (not intensity correlation). This is only computed when there are at least 2 valid spot channels for a given feature.

#### Exported tables (Spots)

**Cells table** (one per segmentation):

- `label_id` - Cell label ID from the selected segmentation.
- `centroid_<axis>_pixels` - Cell centroid in pixels (`y/x` for 2D, `z/y/x` for 3D).
- `centroid_<axis>_um` - Cell centroid in micrometers when physical pixel sizes are available.
- Morphology columns (same naming as Markers): e.g., `morph_area`, `morph_volume`, `morph_*`.
- `overlaps_with` - Semicolon-separated overlapping labels from other configured segmentations in the same feature.
- ROI columns: `included_in_roi_<name>` and/or `excluded_from_roi_<name>`.
- `<channel>_spot_count` - Number of spots assigned to that cell for each configured channel.
- `<channel>_spot_mean_intensity` - Mean of per-spot mean intensities for spots assigned to that cell.
- `colocalization_event_count` (when enabled) - Count of unique overlapping spot pairs within the same cell.

> `<channel>` is derived from the channel **Name** (or the image layer name if Name is empty), sanitized to lowercase with underscores.

**Spots table** (one per segmentation):

- `spot_id` - Unique identifier within channel.
- `cell_id` - Parent cell label ID.
- `channel` - Channel label (custom **Name** if provided, otherwise the image layer name).
- `centroid_<axis>_pixels` - Spot centroid in pixels.
- `centroid_<axis>_um` - Spot centroid in micrometers when physical pixel sizes are available.
- `spot_area_pixels` (2D) or `spot_volume_pixels` (3D) - Spot size in pixel units.
- `spot_area_um2` (2D) or `spot_volume_um3` (3D) - Spot size in physical units when pixel sizes are available.
- `spot_mean_intensity` - Mean intensity of the spot region in the selected image channel.
- ROI columns: `included_in_roi_<name>` and/or `excluded_from_roi_<name>`, evaluated at the spot centroid.
- `colocalizes_with` (when enabled) - Semicolon-separated list of overlapping spots as `<channel_label>:<spot_id>`.

## Output structure

Results are saved to: `<output_folder>/<output_name>/<feature_name>/`

Each feature creates its own subfolder containing:
- One file per segmentation (Markers).
- Two files per segmentation: `*_cells` and `*_spots` (Spots).
- `feature_settings.json` (feature configuration snapshot and run metadata).

**File naming:**
- Markers: `<segmentation_label>.<format>`.
- Spots: `<segmentation_label>_cells.<format>` and `<segmentation_label>_spots.<format>`.
