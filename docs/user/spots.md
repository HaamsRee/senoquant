# Spots

The Spots tab provides spot detection and colocalization visualization for analyzing fluorescent spots in your images.

## Interface overview

### Spot detection section

**Controls:**

- **Image layer** (dropdown): Select the image layer containing spots to detect.
- **Detector** (dropdown): Choose a spot detection algorithm.
- **Settings** (dynamic panel): Detector-specific parameters.
- **Min size** (spin box): Minimum spot size in pixels (0 = no minimum filter). This is area for 2D and volume for 3D.
- **Max size** (spin box): Maximum spot size in pixels (0 = no maximum filter). This is area for 2D and volume for 3D.
- **Run** (button): Execute spot detection on the selected image.

**Size filtering:**
After detection, spots smaller than min size or larger than max size are automatically removed. This helps eliminate noise (single pixels) and large artifacts.

### Colocalization section

**Controls:**

- **Labels A** (dropdown): First labels layer.
- **Labels B** (dropdown): Second labels layer.
- **Visualize** (button): Compute intersection and visualize overlaps.

**Output:**
Creates a Points layer named `{labels_A}_{labels_B}_colocalization` with yellow ring markers at overlap locations.

## Available detectors

| Detector | Algorithm | Best for |
| --- | --- | --- |
| `ufish` | [U-FISH](https://github.com/UFISH-Team/U-FISH/tree/main) | Spots in 2D and 3D immunofluorescence images |

## Output layers

- Spot detection outputs `<image layer>_<detector>_spot_labels`.

## Detector settings

### ufish

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Threshold** | float | 0.5 | 0.0 - 1.0 | Detection threshold (lower = more spots) |

