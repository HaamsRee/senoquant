# Visualization

The Visualization tab generates summary plots from quantification exports.

## Interface overview

### Input section

**Controls:**

- **Input folder** (browse field): Folder containing quantification tables (`.csv`, `.xlsx`, `.xls`).
- **Extensions** (text field): File extensions to search for in the input folder.

**Behavior notes:**

- SenoQuant reads the first matching table to discover marker columns.
- Marker columns are detected from headers ending with `_mean_intensity`.
- If a JSON file is present, threshold values are auto-loaded when possible.

### Marker selection and thresholding section

**Controls:**

- **Select All / Deselect All** (buttons): Toggle all marker include checkboxes.
- **Include** (checkbox per row): Include marker in downstream plotting.
- **Marker** (read-only): Marker name parsed from quantification columns.
- **Threshold** (text field per row): Optional threshold value for each marker.

**Behavior notes:**

- Thresholds are applied per marker before plotting.
- Empty threshold values are treated as automatic/no override.

### Plots section

**Controls:**

- **Plot Type** (dropdown): Select the visualization type.

**Available plot types:**

- **Spatial Plot**
- **UMAP**
- **Double Expression**

### Plot preview section

**Controls:**

- **Process** (button): Generate preview outputs using current settings.

**Behavior notes:**

- PNG plots are shown directly in the preview pane.
- SVG and PDF plots are shown as clickable links.
- Running Process again clears previous previews.

### Output section

**Controls:**

- **Output path** (browse field): Destination folder for saved plots.
- **Plot name** (text field): Base name for saved files.
- **Format** (dropdown): `png`, `svg`, or `pdf`.
- **Save Plot** (button): Copy the latest processed plots to the output folder.

## Plot behavior details

### Spatial Plot

- Uses detected X/Y coordinate columns for point positions.
- Colors by the first numeric column that is not X or Y.
- Marker filtering keeps selected marker intensity columns and drops deselected marker intensity columns.

### UMAP

- Uses selected marker intensity columns as UMAP input features.
- Requires at least two numeric input columns.
- Generates a 2D embedding scatter plot.

### Double Expression

- Requires exactly two selected markers.
- Uses thresholds for each selected marker.
- Draws:
  - Negative cells (background, light gray).
  - Marker 1 positive only (red).
  - Marker 2 positive only (blue).
  - Double positive (green).

## Output naming

- If **Plot name** is set and a single output is produced, filename is `<plot_name>.<ext>`.
- If multiple outputs are produced, filenames are `<plot_name>_1.<ext>`, `<plot_name>_2.<ext>`, etc.
- If **Plot name** is blank, SenoQuant prefixes filenames with the plot type.

## Tips

- Use quantification outputs from the same image cohort for consistent marker columns.
- Check X/Y coordinate column names in your exported tables if spatial plots return no output.
- For Double Expression, make sure both selected markers exist as `<marker>_mean_intensity`.
