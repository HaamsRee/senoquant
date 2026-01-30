# Quantification

The Quantification tab builds a list of features to extract and exports the
results to disk.

## Workflow

1. Click `Add feature` to add a feature block.
2. Set a name and pick a feature type.
3. Configure channels, segmentations, and ROIs as needed.
4. Choose an output path, output name, and format (`csv` or `xlsx`).
5. Click `Process`.

## Feature types

### Markers

Marker features measure channel intensity and morphological properties within segmentation labels.
The configuration supports:

- One or more segmentation label layers.
- One or more image channels (with optional threshold settings).
- Optional ROIs (include or exclude) based on Shapes layers.

#### Exported columns

Each marker feature export includes:

**Shape and morphology** (prefixed with `morph_`):
- `area` (2D) or `volume` (3D): Size in pixels
- `area_um2` (2D) or `volume_um3` (3D): Physical size in micrometers
- `circularity` (2D only): 4π·area/perimeter² (1.0 is a perfect circle)
- `eccentricity`: Ellipse eccentricity (0 is circular, 1 is elongated)
- `extent`: Ratio of region area to bounding box area
- `feret_diameter_max`: Maximum Feret diameter
- `major_axis_length`: Semi-major axis of fitted ellipse
- `minor_axis_length`: Semi-minor axis of fitted ellipse
- `aspect_ratio`: Ratio of major to minor axis lengths
- `orientation`: Angle of major axis (radians)
- `perimeter` (2D only): Region perimeter estimate
- `perimeter_crofton` (2D only): Crofton perimeter estimate
- `solidity`: Ratio of region area to convex hull area

**Centroid position** (in pixel coordinates):
- `centroid_row`, `centroid_col` (2D)
- `centroid_plane`, `centroid_row`, `centroid_col` (3D)

**Channel intensity** (one per configured channel):
- Mean, median, min, max, and sum intensity values
- Standard deviation and variance of intensity
- Threshold-based metrics if thresholds are configured

### Spots

Spots features export measurements for spot labels. The configuration
supports:

- Optional segmentation filters to restrict spots.
- One or more channels, each with an associated spots labels layer.
- Optional ROIs (include or exclude) based on Shapes layers.
- Optional colocalization export flag.

## Output structure

Quantification output is written to `output_path/output_name` if an output
name is provided. If `output_path` is empty, the current working directory
is used. Each feature exports into its own folder named from the feature
name (or the feature type if no name is provided), with non-alphanumeric
characters replaced for filesystem safety.
