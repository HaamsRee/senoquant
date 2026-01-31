# Spots

The Spots tab provides spot detection and colocalization visualization for analyzing fluorescent spots in your images.

## Interface Overview

### Spot Detection Section

**Controls:**

- **Image layer** (dropdown): Select the image layer containing spots to detect
- **Detector** (dropdown): Choose a spot detection algorithm
- **Settings** (dynamic panel): Detector-specific parameters
- **Min size** (spin box): Minimum spot size in pixels (0 = no minimum filter)
- **Max size** (spin box): Maximum spot size in pixels (0 = no maximum filter)
- **Run** (button): Execute spot detection on the selected image

**Size Filtering:**
After detection, spots smaller than min size or larger than max size are automatically removed. This helps eliminate noise (single pixels) and large artifacts.

### Colocalization Section

**Controls:**

- **Labels A** (dropdown): First labels layer
- **Labels B** (dropdown): Second labels layer
- **Run** (button): Compute intersection and visualize overlaps

**Output:**
Creates a Points layer named `{labels_A}_{labels_B}_colocalization` with yellow ring markers at overlap locations.

## Available Detectors

| Detector | Algorithm | Best For |
| --- | --- | --- |
| `udwt` | Undecimated B3-spline wavelet transform | Multi-scale spot detection, various sizes |
| `rmp` | Rotational morphological processing | Spot detection with rotational analysis |

## Detector Settings

### udwt (Undecimated Wavelet Transform)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Product threshold (ld)** | float | 1.0 | 0.0 - 10.0 | Detection threshold (lower = more sensitive) |
| **Force 2D for 3D** | bool | false | - | Use 2D wavelets on 3D images (for spots in XY only) |
| **Enable scale 1** | bool | true | - | Detect smallest spots |
| **Scale 1 sensitivity** | float | 100.0 | 1.0 - 100.0 | Sensitivity for scale 1 (requires Enable scale 1) |
| **Enable scale 2** | bool | true | - | Detect medium spots |
| **Scale 2 sensitivity** | float | 100.0 | 1.0 - 100.0 | Sensitivity for scale 2 (requires Enable scale 2) |
| **Enable scale 3** | bool | true | - | Detect larger spots |
| **Scale 3 sensitivity** | float | 100.0 | 1.0 - 100.0 | Sensitivity for scale 3 (requires Enable scale 3) |
| **Enable scale 4** | bool | false | - | Detect very large structures |
| **Scale 4 sensitivity** | float | 100.0 | 1.0 - 100.0 | Sensitivity for scale 4 (requires Enable scale 4) |
| **Enable scale 5** | bool | false | - | Detect largest structures |
| **Scale 5 sensitivity** | float | 100.0 | 1.0 - 100.0 | Sensitivity for scale 5 (requires Enable scale 5) |

**Multi-scale strategy:**
- Scale 1: Smallest spots (finest details)
- Scale 2: Medium-sized spots
- Scale 3: Larger spots
- Scales 4-5: Very large structures (typically disabled)

### rmp (Rotational Morphological Processing)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Denoising kernel length** | int | 2 | 2 - 9999 | Kernel size for denoising (requires Enable denoising) |
| **Extraction kernel length** | int | 10 | 1 - 9999 | Kernel size for morphological operations |
| **Angle spacing** | int | 5 | 1 - 10 | Angular resolution (smaller = finer) |
| **Manual threshold** | float | 0.05 | 0.0 - 1.0 | Detection threshold (requires Auto threshold=false) |
| **Auto threshold** | bool | true | - | Automatically determine threshold |
| **Enable denoising** | bool | true | - | Pre-filter image before detection |
| **Use 3D** | bool | false | - | Enable 3D detection |
