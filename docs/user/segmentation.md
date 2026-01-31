# Segmentation

The Segmentation tab provides two sections for segmenting nuclei and cytoplasm in your images.

## Interface Overview

### Nuclear Segmentation Section

**Controls:**

- **Image layer** (dropdown): Select the image layer containing nuclear staining
- **Model** (dropdown): Choose a nuclear segmentation model
- **Settings** (dynamic panel): Model-specific parameters that update based on selected model
- **Run** (button): Execute nuclear segmentation on the selected image

### Cytoplasmic Segmentation Section

**Controls:**

- **Image layer** (dropdown): Select the image layer containing cytoplasmic staining
- **Nuclear layer** (dropdown): Optional nuclear segmentation mask (required for some models)
- **Model** (dropdown): Choose a cytoplasmic segmentation model
- **Settings** (dynamic panel): Model-specific parameters
- **Run** (button): Execute cytoplasmic segmentation

## Available Models

### Nuclear Segmentation Models

| Model | Description | Dimensionality | Technology |
| --- | --- | --- | --- |
| `default_2d` | Fine-tuned StarDist 2D model | 2D | ONNX Runtime |
| `default_3d` | Fine-tuned StarDist 3D model | 3D | ONNX Runtime |
| `cpsam` | Cellpose SAM integration | 2D/3D | Cellpose |

### Cytoplasmic Segmentation Models

| Model | Description | Input Requirements | Use Case |
| --- | --- | --- | --- |
| `cpsam` | Cellpose SAM cytoplasmic | Cytoplasm image (nuclear optional) | General cytoplasm segmentation |
| `nuclear_dilation` | Dilates nuclear masks | Nuclear mask only | Weak cytoplasmic staining |
| `perinuclear_rings` | Ring-shaped regions | Nuclear mask only | Perinuclear marker analysis |

## Model Settings

Each model exposes settings through a dynamic UI generated from `details.json`:

**Setting Types:**

- **Float**: Spin box with decimal precision, min/max range
- **Integer**: Spin box with whole numbers, min/max range
- **Boolean**: Checkbox for on/off options

**Conditional Settings:**

Some settings are enabled/disabled based on other settings:
- Example: `pmin` and `pmax` are only enabled when `normalize` is checked

## Output layers

- Nuclear segmentation outputs `<image layer>_<model>_nuc_labels`.
- Cytoplasmic segmentation outputs `<image layer>_<model>_cyto_labels`.
- Labels layers are created with a contour value of 2.

## Preloading models

If `Preload segmentation models on startup` is enabled in Settings,
SenoQuant instantiates all discovered segmentation models when the tab
loads. This can reduce the first-run latency for models.

## Settings Reference

### default_2d (StarDist 2D)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Object diameter (px)** | float | 30.0 | 1.0 - 500.0 | Expected diameter of nuclei in pixels |
| **Prob threshold** | float | 0.496 | 0.0 - 1.0 | Probability threshold for nucleus detection |
| **NMS threshold** | float | 0.3 | 0.0 - 1.0 | Non-maximum suppression threshold |
| **Normalize** | bool | true | - | Enable intensity normalization |
| **Percentile min** | float | 1.0 | 0.0 - 100.0 | Lower percentile for normalization (requires Normalize=true) |
| **Percentile max** | float | 99.8 | 0.0 - 100.0 | Upper percentile for normalization (requires Normalize=true) |

### default_3d (StarDist 3D)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Object diameter (px)** | float | 30.0 | 1.0 - 500.0 | Expected diameter of nuclei in pixels |
| **Prob threshold** | float | 0.445 | 0.0 - 1.0 | Probability threshold for nucleus detection |
| **NMS threshold** | float | 0.3 | 0.0 - 1.0 | Non-maximum suppression threshold |
| **Normalize** | bool | true | - | Enable intensity normalization |
| **Percentile min** | float | 1.0 | 0.0 - 100.0 | Lower percentile for normalization (requires Normalize=true) |
| **Percentile max** | float | 99.8 | 0.0 - 100.0 | Upper percentile for normalization (requires Normalize=true) |

### cpsam (Cellpose SAM)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Diameter** | float | 30.0 | 0.1 - 1000.0 | Expected cell/nucleus diameter |
| **Flow threshold** | float | 0.4 | 0.0 - 2.0 | Flow field threshold |
| **Cellprob threshold** | float | 0.0 | -6.0 - 6.0 | Cell probability threshold |
| **Number of iterations** | int | 0 | 0 - 9999 | Refinement iterations (0 = automatic) |
| **Use 3D** | bool | false | - | Enable 3D processing |
| **Normalize** | bool | true | - | Enable intensity normalization |

### nuclear_dilation (Cytoplasmic)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Dilation iterations** | int | 5 | 1 - 100 | Number of binary dilation iterations to expand nuclear mask |

**Use case:** When cytoplasmic staining is weak or unavailable, this model expands the nuclear mask outward to approximate cytoplasmic boundaries.

### perinuclear_rings (Cytoplasmic)

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Inner erosion (px)** | int | 2 | 1 - 50 | Pixels to erode inward from nuclear boundary |
| **Outer dilation (px)** | int | 5 | 0 - 50 | Pixels to dilate outward from nuclear boundary |

**Use case:** Creates ring-shaped labels for analyzing perinuclear markers (e.g., ER, Golgi, nuclear envelope).
