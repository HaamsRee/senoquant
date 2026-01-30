# Spots

The Spots tab provides spot detection and colocalization visualization.

## Spot detection

1. Select an image layer.
2. Choose a detector.
3. Configure detector settings (dynamic per detector).
4. Run detection.

Detectors are discovered from `src/senoquant/tabs/spots/models`.

### Available detectors

| Detector | Description |
| --- | --- |
| `rmp` | Placeholder details for the rmp spot detector |
| `udwt` | Undecimated B3-spline wavelet spot detector |

### Output labels

Detectors output labels layers named:

- `<image layer>_<detector>_spot_labels`

Labels layers are created with a contour value of 1.

## Colocalization

The colocalization section visualizes overlaps between two labels layers.

- Select two labels layers with matching shapes.
- SenoQuant computes the intersection and adds a points layer.
- Output layer name: `<labels A>_<labels B>_colocalization`.
- Points are rendered as yellow rings.

If no overlap is found, a notification is displayed.

## Settings reference

### rmp

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `denoising_kernel_length` | int | 2 | 2 - 9999 | Enabled when `enable_denoising` is true. |
| `extraction_kernel_length` | int | 10 | 1 - 9999 | - |
| `angle_spacing` | int | 5 | 1 - 10 | - |
| `manual_threshold` | float | 0.05 | 0.0 - 1.0 | Disabled when `auto_threshold` is true. |
| `auto_threshold` | bool | true | - | - |
| `enable_denoising` | bool | true | - | - |
| `use_3d` | bool | false | - | - |

### udwt

| Key | Type | Default | Range | Notes |
| --- | --- | --- | --- | --- |
| `ld` | float | 1.0 | 0.0 - 10.0 | - |
| `force_2d` | bool | false | - | - |
| `scale_1_enabled` | bool | true | - | - |
| `scale_1_sensitivity` | float | 100.0 | 1.0 - 100.0 | Enabled when `scale_1_enabled` is true. |
| `scale_2_enabled` | bool | true | - | - |
| `scale_2_sensitivity` | float | 100.0 | 1.0 - 100.0 | Enabled when `scale_2_enabled` is true. |
| `scale_3_enabled` | bool | true | - | - |
| `scale_3_sensitivity` | float | 100.0 | 1.0 - 100.0 | Enabled when `scale_3_enabled` is true. |
| `scale_4_enabled` | bool | false | - | - |
| `scale_4_sensitivity` | float | 100.0 | 1.0 - 100.0 | Enabled when `scale_4_enabled` is true. |
| `scale_5_enabled` | bool | false | - | - |
| `scale_5_sensitivity` | float | 100.0 | 1.0 - 100.0 | Enabled when `scale_5_enabled` is true. |
