# Cross-Reference Columns for Marker Export

## Overview

The marker export feature now includes three reference columns that track the origin and relationships of exported marker regions:

1. **`file_path`** - Original image file path
2. **`segmentation_type`** - Segmentation type ("nuclear" or "cytoplasmic")
3. **`overlaps_with`** - Cross-segmentation spatial overlaps (when applicable)

## File Path Column

The `file_path` column stores the original image file path for each exported marker region. This enables tracking which image each region came from, particularly useful when processing batch files or multi-file datasets.

**Source:** Extracted from the first channel layer's metadata

**Example value:** `/path/to/image_0001.tif`

## Segmentation Type Column

The `segmentation_type` column indicates whether the region was derived from nuclear or cytoplasmic segmentation.

**Possible values:**
- `"nuclear"` - Region from nuclear segmentation
- `"cytoplasmic"` - Region from cytoplasmic segmentation

**Example workflow:**
```python
from senoquant.tabs.quantification.features.marker.export import _add_reference_columns

rows = [{"label_id": 1, "area": 100}]
labels = segmentation_labels_array
label_ids = np.array([1])

# Add reference columns
_add_reference_columns(
    rows,
    labels,
    label_ids,
    file_path="/path/to/image.tif",
    segmentation_type="nuclear"
)

# Result: rows[0] now has "file_path" and "segmentation_type" keys
```

## Cross-Segmentation Overlap References

The `overlaps_with` column enables tracking which regions from different segmentations overlap spatially. This is particularly useful when both nuclear and cytoplasmic segmentations are applied to the same image.

### How It Works

1. **Spatial Overlap Detection:** Identifies which nuclear labels overlap with which cytoplasmic labels (and vice versa) by checking pixel-level intersections.

2. **Reference Format:** Overlaps are stored as semicolon-separated strings using the format `segmentation_name_label_id`.

   **Example:** `"cytoplasmic_5;cytoplasmic_12"` indicates the nuclear region overlaps with cytoplasmic regions 5 and 12.

### Example

```python
import numpy as np
from senoquant.tabs.quantification.features.marker.export import (
    _build_cross_segmentation_map,
    _add_cross_reference_column,
)

# Define label images
nuclear_labels = np.array([
    [1, 1, 2],
    [1, 1, 2],
    [3, 3, 0]
], dtype=np.uint16)

cytoplasmic_labels = np.array([
    [10, 10, 20],
    [10, 10, 20],
    [0, 0, 0]
], dtype=np.uint16)

# Build cross-reference map
all_segs = {
    "nuclear": (nuclear_labels, np.array([1, 2, 3])),
    "cytoplasmic": (cytoplasmic_labels, np.array([10, 20])),
}
cross_map = _build_cross_segmentation_map(all_segs)

# Add cross-reference column to nuclear export rows
nuclear_rows = [
    {"label_id": 1},
    {"label_id": 2},
]
nuclear_ids = np.array([1, 2])

_add_cross_reference_column(
    nuclear_rows,
    "nuclear",
    nuclear_ids,
    cross_map
)

# Result:
# nuclear_rows[0]["overlaps_with"] == "cytoplasmic_10;cytoplasmic_20"
# nuclear_rows[1]["overlaps_with"] == "cytoplasmic_10;cytoplasmic_20"
```

### Empty Overlaps

Regions with no spatial overlap with other segmentations have an empty string in the `overlaps_with` column:

```python
row["overlaps_with"] == ""  # No overlaps detected
```

## Implementation Details

### _add_reference_columns()

Adds `file_path` and `segmentation_type` columns to export rows.

```python
def _add_reference_columns(
    rows: list[dict],
    labels: np.ndarray,
    label_ids: np.ndarray,
    file_path: str | None,
    segmentation_type: str,
) -> list[str]:
    """
    Parameters
    ----------
    rows
        Output row dictionaries to update in-place.
    labels
        Label image with integer ids.
    label_ids
        Label ids corresponding to the output rows.
    file_path
        Original file path from metadata (or None).
    segmentation_type
        Type of segmentation ("nuclear" or "cytoplasmic").

    Returns
    -------
    list of str
        Column names added to rows.
    """
```

### _build_cross_segmentation_map()

Builds a spatial overlap index across multiple segmentations.

```python
def _build_cross_segmentation_map(
    all_segmentations: dict[str, tuple[np.ndarray, np.ndarray]],
) -> dict[tuple[str, int], list[tuple[str, int]]]:
    """
    Parameters
    ----------
    all_segmentations
        Mapping from segmentation name to (labels, label_ids) tuple.

    Returns
    -------
    dict
        Mapping from (seg_name, label_id) to list of overlapping
        (other_seg_name, overlapping_label_id) tuples.
    """
```

### _add_cross_reference_column()

Populates the `overlaps_with` column using a cross-segmentation map.

```python
def _add_cross_reference_column(
    rows: list[dict],
    segmentation_name: str,
    label_ids: np.ndarray,
    cross_map: dict,
) -> str:
    """
    Parameters
    ----------
    rows
        Output row dictionaries to update in-place.
    segmentation_name
        Name of this segmentation.
    label_ids
        Label ids corresponding to the output rows.
    cross_map
        Cross-segmentation overlap mapping from _build_cross_segmentation_map.

    Returns
    -------
    str
        Column name added ("overlaps_with").
    """
```

## Testing

Comprehensive tests are available in:
`tests/senoquant/tabs/quantification/features/marker/test_export_references.py`

Tests cover:
- Adding file_path and segmentation_type columns
- Handling missing file_path (None value)
- Different segmentation type assignments
- Building cross-segmentation maps with single and multiple segmentations
- Detecting spatial overlaps correctly
- Handling empty overlaps
- Full integration workflows

## Notes

1. **File path availability:** The `file_path` column is only added if the first channel layer has metadata. If unavailable, the column is skipped.

2. **Segmentation type:** Should be one of `"nuclear"` or `"cytoplasmic"`. Other values are used as-is in the export.

3. **Cross-segmentation references:** Building the cross-map requires access to all label images simultaneously. When processing batch jobs, ensure all segmentation outputs are available before calling `_build_cross_segmentation_map()`.

4. **Performance:** For large label images with many regions, building the cross-map can be computationally intensive. Consider caching results if processing multiple files with the same segmentation setup.

5. **2D vs 3D:** All functions handle both 2D and 3D images transparently. Spatial overlap detection uses numpy operations that work on any dimensionality.
