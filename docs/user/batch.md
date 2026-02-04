# Batch processing

The Batch tab runs segmentation, spot detection, and quantification across folders of images. It's currently a bit buggy and under active development, so please report issues on [GitHub](https://github.com/HaamsRee/senoquant/issues).

## Interface overview

### Input section

**Controls:**

- **Input folder** (browse field): Select the folder containing input images.
- **Extensions** (text field): Comma-separated file extensions to include.
- **Include subfolders** (checkbox): Recursively scan nested folders.
- **Process all scenes** (checkbox): Process all scenes in multi-scene files.
- **Load profile** and **Save profile** (buttons): Load or save batch settings as a JSON profile.

**Behavior notes:**

- If the extensions field is empty, all files are considered.
- Extensions are normalized to lowercase and a leading dot is added if missing.
- By default, the extensions field is pre-filled with common image formats.

### Channels section

Use channel mappings to define reusable channel names for all dropdowns in the tab.

**Controls:**

- **Add channel** (button): Add a new channel row.
- **Name** (text field): Channel display name (for example, `DAPI`).
- **Index** (spin box): Zero-based channel index in the source image.
- **Delete** (button): Remove that mapping row.

**Behavior notes:**

- If **Name** is left blank, Batch uses the index as the name (for example, `0`).
- Channel names from this section drive nuclear/cytoplasmic/spot channel selectors and quantification layer choices.

### Segmentation section

#### Nuclear segmentation controls

- **Run nuclear segmentation** (checkbox): Enable or disable nuclear segmentation.
- **Nuclear model** (dropdown): Select a nuclear model.
- **Nuclear channel** (dropdown): Select the image channel for nuclear segmentation.
- **Edit nuclear settings** (button): Open the model settings dialog.

#### Cytoplasmic segmentation controls

- **Run cytoplasmic segmentation** (checkbox): Enable or disable cytoplasmic segmentation.
- **Cytoplasmic model** (dropdown): Select a cytoplasmic model.
- **Cytoplasmic channel** (dropdown): Select the image channel for cytoplasmic segmentation.
- **Nuclear channel** (dropdown): Select a nuclear channel when required by the selected model.
- **Edit cytoplasmic settings** (button): Open the model settings dialog.

**Behavior notes:**

- Cytoplasmic models that support `nuclear+cytoplasmic` input enable the nuclear channel selector.
- For models where nuclear input is optional, the label updates to `Nuclear channel (optional)` and includes `(none)` as a valid choice.
- For models where nuclear input is required, the label updates to `Nuclear channel (required)`.

### Spot detection section

**Controls:**

- **Run spot detection** (checkbox): Enable or disable spot detection.
- **Spot detector** (dropdown): Select the spot detector.
- **Edit spot settings** (button): Open detector settings.
- **Minimum spot size (px)** (spin box): Minimum label size after detection (`0` means no minimum filter).
- **Maximum spot size (px)** (spin box): Maximum label size after detection (`0` means no maximum filter).
- **Add spot channel** (button): Add a spot channel row.
- **Spot channel row**: Channel dropdown plus **Delete** button.

**Behavior notes:**

- Spot size filtering is applied after detector output.
- If spot detection is enabled, at least one spot channel must be selected before run.

### Quantification section

The Batch tab embeds the Quantification feature editor with batch-safe options.

**Controls:**

- **Run quantification** (checkbox): Enable or disable quantification.
- Embedded feature editor: Add and configure **Markers** or **Spots** features.

**Batch-mode differences from the Quantification tab:**

- Output-path controls are hidden.
- The Process button is hidden.
- ROI configuration is disabled.
- Threshold controls are disabled.
- Quantification format is set in the Batch **Output** section.

### Output section

**Controls:**

- **Output folder** (browse field): Destination root for batch outputs.
- **Segmentation format** (dropdown): `tif` or `npy` for mask outputs.
- **Quantification format** (dropdown): `xlsx` or `csv`.
- **Overwrite existing outputs** (checkbox): Control behavior when output folders already exist.

**Behavior notes:**

- If output folder is left empty, Batch defaults to `<input_folder>/batch-output`.
- If overwrite is off and a target output folder already exists, that item is skipped.

### Run section

**Controls:**

- **Run batch** (button): Start batch processing.
- **Progress bar**: Shows percent completion.
- **Status label**: Shows current status and per-item progress text.

**Behavior notes:**

- Processing runs in a background thread.
- Progress messages include file name and scene when relevant.
- Completion reports processed, failed, and skipped item counts.
- You must enable at least one processing path (segmentation, spots, or quantification).
- If spot detection is enabled, at least one spot channel is required.

## Processing behavior

For each discovered image file (and each scene, if scene processing is enabled), Batch runs steps in this order:

1. Nuclear segmentation (if enabled).
2. Cytoplasmic segmentation (if enabled).
3. Spot detection (if enabled).
4. Quantification (if enabled and features are configured).

Batch continues processing remaining items even if one item fails.

## Output structure

### Per-image output folders

Batch writes outputs under:

`<output_folder>/<image_base_name>/`

If **Process all scenes** is enabled:

`<output_folder>/<image_base_name>/<scene_name>/`

### Segmentation and spots output names

- Nuclear masks: `<channel>_<model>_nuc_labels.<tif|npy>`.
- Cytoplasmic masks: `<channel>_<model>_cyto_labels.<tif|npy>`.
- Spot masks: `<channel>_<detector>_spot_labels.<tif|npy>`.

### Quantification output layout

Quantification outputs are written into feature folders inside the same per-image (or per-scene) folder:

`<output_folder>/<image_or_scene>/<feature_name_sanitized>/`

Within each feature folder:

- Markers feature: One file per segmentation.
- Spots feature: `<segmentation_label>_cells.<format>` and `<segmentation_label>_spots.<format>`.

Feature folder names are normalized to lowercase and spaces become underscores.

### Example layout

```text
batch-output/
  sample_01/
    dapi_default_2d_nuc_labels.tif
    fitc_ufish_spot_labels.tif
    if_markers/
      dapi_default_2d_nuc_labels.xlsx
    if_spots/
      dapi_default_2d_nuc_labels_cells.xlsx
      dapi_default_2d_nuc_labels_spots.xlsx
  sample_02/
    Scene_0/
      ...
    Scene_1/
      ...
```

## Tips

- Keep channel mapping complete before configuring feature dropdowns.
- Verify detector/model settings on one representative image before full batch runs.
- Use profiles for repeat experiments and parameter reuse.
- Leave overwrite off when resuming interrupted runs.
