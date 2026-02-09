# Spots

The Spots tab provides spot detection and colocalization visualization for analyzing fluorescent spots in your images.

## Interface overview

### Spot detection section

**Controls:**

- **Image layer** (dropdown): Select the image layer containing spots to detect.
- **Detector** (dropdown): Choose a spot detection algorithm.
- **Settings** (dynamic panel): Detector-specific parameters.
- **Minimum diameter** (spin box): Minimum spot diameter in pixels (`0` = no minimum filter).
- **Maximum diameter** (spin box): Maximum spot diameter in pixels (`0` = no maximum filter).
- **Run** (button): Execute spot detection on the selected image.

**Diameter filtering behavior:**
After detection, connected components are filtered against diameter-derived thresholds:

- For 2D labels, thresholds are converted to effective area: `A = pi * (d / 2)^2`.
- For 3D labels, thresholds are converted to effective volume: `V = (4/3) * pi * (d / 2)^3`.

Components with pixel/voxel counts outside the computed range are removed.

### Colocalization section

**Controls:**

- **Labels A** (dropdown): First labels layer.
- **Labels B** (dropdown): Second labels layer.
- **Visualize** (button): Compute intersection and visualize overlaps.

**Output:**
Creates a Points layer named `{labels_A}_{labels_B}_colocalization` with yellow ring markers at overlap locations.

## Available detectors

| Detector | Algorithm | Description |
| --- | --- | --- |
| `rmp` | Rotational Morphological Processing (RMP) | Spot extraction with rotating images and thin structuring elements. Compatible with 2D and 3D images. |
| `ufish` | [U-FISH](https://github.com/UFISH-Team/U-FISH/tree/main) | Spot extraction with a compact deep learning model for 2D and 3D images. |

## Output layers

- Spot detection outputs `<image layer>_<detector>_spot_labels`.

## Detector settings

### rmp

Source: `src/senoquant/tabs/spots/models/rmp/details.json` and `src/senoquant/tabs/spots/models/rmp/model.py`.  

Method reference: [Rotational Morphological Processing for spot detection](https://link.springer.com/article/10.1186/1471-2105-11-373).

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Spot diameter (px)** | int | 10 | 3 - 9999 | Expected spot diameter used by the extraction structuring element. |
| **Auto threshold** | bool | true | n/a | Uses Otsu thresholding on the normalized response. |
| **Manual threshold** | float | 0.50 | 0.0 - 1.0 | Fixed threshold when **Auto threshold** is off. Disabled when auto-thresholding is enabled. |

RMP simplifications:
- Angle spacing is fixed internally to `5` degrees.
- Wavelet denoising is always enabled (both before and after top-hat extraction).

### ufish

Source: `src/senoquant/tabs/spots/models/ufish/details.json` and `src/senoquant/tabs/spots/models/ufish/model.py`.

| Setting | Type | Default | Range | Description |
| --- | --- | --- | --- | --- |
| **Spot size** | float | 1.0 | 0.25 - 4.0 | Spot-scale control. `1.0` is default, `>1` biases detection toward larger spots, `<1` toward smaller spots. |
| **Threshold** | float | 0.5 | 0.0 - 1.0 | Foreground threshold on the enhanced response (lower = more spots). |

UFISH simplification:
- Wavelet denoising is always enabled before enhancement/segmentation.
