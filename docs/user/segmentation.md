# Segmentation

The Segmentation tab provides two sections for segmenting nuclei and cytoplasm in your images.

## Interface overview

### Nuclear segmentation section

**Controls:**

- **Nuclear layer** (dropdown): Select the image layer containing nuclear staining.
- **Model** (dropdown): Choose a nuclear segmentation model.
- **Settings** (dynamic panel): Model-specific parameters that update based on selected model.
- **Run** (button): Execute nuclear segmentation on the selected image.

### Cytoplasmic segmentation section

**Controls:**

- **Cytoplasmic layer** (dropdown): Select the image layer containing cytoplasmic staining.
- **Nuclear layer** (dropdown): Optional nuclear segmentation mask (required for some models).
- **Model** (dropdown): Choose a cytoplasmic segmentation model.
- **Settings** (dynamic panel): Model-specific parameters.
- **Run** (button): Execute cytoplasmic segmentation.

## Available models

### Nuclear segmentation models

| Model | Description | Dimensionality |
| --- | --- | --- |
| `default_2d` | Fine-tuned StarDist model for 2D nuclei. | 2D |
| `default_3d` | Fine-tuned StarDist model for 3D nuclei. | 3D |
| `cpsam` | Cellpose SAM model for nuclei. | 2D/3D |

### Cytoplasmic segmentation models

| Model | Description | Input requirements | Use case |
| --- | --- | --- | --- |
| `cpsam` | Cellpose SAM cytoplasmic. | Cytoplasm image (nuclear optional). | General cytoplasm segmentation. |
| `nuclear_dilation` | Dilates nuclear masks. | Nuclear mask only. | Weak or missing cytoplasmic staining. |
| `perinuclear_rings` | For ring-shaped regions. | Nuclear mask only. | Perinuclear marker analysis. |

## Output layers

- Nuclear segmentation outputs `<image layer>_<model>_nuc_labels`.
- Cytoplasmic segmentation outputs `<image layer>_<model>_cyto_labels`.

## Preloading models

If `Preload segmentation models on startup` is enabled in **Settings**,
SenoQuant instantiates all discovered segmentation models when the tab
loads. This can reduce the first-run latency for models. This is the default behavior for now and disabling it doesn't persist between sessions.

## Settings reference

This section mirrors the model metadata in the plugin. Use it as a guide for choosing the right model and tuning its parameters.

### default_2d (StarDist 2D)

**Best for:** 2D nuclei with clear boundaries (single z-slice or 2D projections).

**How it works:** StarDist predicts star-convex polygons around nuclei and uses non-maximum suppression to separate instances.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Object diameter (px)** | float | 30.0 | 1.0 - 500.0 | Expected diameter of nuclei in pixels. Adjust as needed. |
| **Prob threshold** | float | 0.496 | 0.0 - 1.0 | Confidence threshold for accepting nuclei. Lower detects more, higher is stricter. |
| **NMS threshold** | float | 0.3 | 0.0 - 1.0 | Non-maximum suppression threshold for separating instances. Lower splits more. |
| **Normalize** | bool | true | - | Normalize intensities before inference. |
| **Percentile min** | float | 1.0 | 0.0 - 100.0 | Lower percentile for normalization (enabled when Normalize is on). |
| **Percentile max** | float | 99.8 | 0.0 - 100.0 | Upper percentile for normalization (enabled when Normalize is on). |

### default_3d (StarDist 3D)

**Best for:** 3D stacks where nuclei extend across multiple z-planes.

**How it works:** StarDist 3D predicts star-convex polyhedra in volumetric data.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Object diameter (px)** | float | 30.0 | 1.0 - 500.0 | Expected diameter of nuclei in pixels. |
| **Prob threshold** | float | 0.445 | 0.0 - 1.0 | Confidence threshold for accepting nuclei. |
| **NMS threshold** | float | 0.3 | 0.0 - 1.0 | Non-maximum suppression threshold for separating instances. |
| **Normalize** | bool | true | - | Normalize intensities before inference. |
| **Percentile min** | float | 1.0 | 0.0 - 100.0 | Lower percentile for normalization (enabled when Normalize is on). |
| **Percentile max** | float | 99.8 | 0.0 - 100.0 | Upper percentile for normalization (enabled when Normalize is on). |

### cpsam (Cellpose SAM)

**Best for:** General purpose nuclear/cytoplasmic segmentation.

**How it works:** Cellpose with SAM encoder.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Diameter** | float | 30.0 | 0.1 - 1000.0 | Expected diameter of cells or nuclei. |
| **Flow threshold** | float | 0.4 | 0.0 - 2.0 | Threshold for flow field quality; Higher = accept more masks. |
| **Cellprob threshold** | float | 0.0 | -6.0 - 6.0 | Threshold on cell probability; Higher = accept fewer masks. |
| **Number of iterations** | int | 0 | 0 - 9999 | Iterations of dynamic simulation (0 = automatic; For larger/longer cells, try a higher value like 2000). |
| **3D** | bool | false | - | Enable 3D processing for stacks. |
| **Normalize** | bool | true | - | Normalize intensities before inference. |

### nuclear_dilation (Cytoplasmic)

**Best for:** Approximating cytoplasm when you only have nuclear masks.

**How it works:** Binary dilation expands nuclear labels outward by a fixed number of pixels.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Dilation iterations** | int | 5 | 1 - 100 | Number of binary dilation iterations to expand nuclear masks. |

### perinuclear_rings (Cytoplasmic)

**Best for:** Perinuclear marker quantification (eg., nuclear envelope).

**How it works:** Erodes nuclei inward and dilates outward to form a ring mask.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Inner erosion (px)** | int | 2 | 1 - 50 | Pixels to erode inward from the nuclear boundary. |
| **Outer dilation (px)** | int | 5 | 0 - 50 | Pixels to dilate outward from the nuclear boundary. |

> **Note:** The minimum inner erosion is set to 1 pixel as needed by the logic to associate across segmentation masks in Quantification.