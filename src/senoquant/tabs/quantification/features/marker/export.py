"""Marker feature export logic.

This module serializes per-label morphology and per-channel intensity
summaries for the marker feature. When thresholds are enabled for a
channel, both raw and thresholded intensity columns are exported along
with a JSON metadata file recording the threshold settings.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path
from typing import Iterable, Optional, Sequence, TYPE_CHECKING

import numpy as np
from skimage.measure import regionprops_table

from senoquant.utils import layer_data_asarray
from .config import MarkerFeatureData
from .morphology import add_morphology_columns
from ..base import FeatureConfig

if TYPE_CHECKING:
    from ..roi import ROIConfig

def export_marker(
    feature: FeatureConfig,
    temp_dir: Path,
    viewer=None,
    export_format: str = "csv",
    enable_thresholds: bool = True,
) -> Iterable[Path]:
    """Export marker feature outputs into a temporary directory.

    Parameters
    ----------
    feature : FeatureConfig
        Marker feature configuration to export.
    temp_dir : Path
        Temporary directory where outputs should be written.
    viewer : object, optional
        Napari viewer instance used to resolve layers by name.
    export_format : str, optional
        File format for exports (``"csv"`` or ``"xlsx"``).
    enable_thresholds : bool, optional
        Whether thresholded outputs should be computed.

    Returns
    -------
    iterable of Path
        Paths to files produced by the export routine. Each segmentation
        produces one table, and a shared ``marker_thresholds.json`` file
        is emitted when channels are configured.

    Notes
    -----
    If an image layer does not match a labels layer in shape, that channel
    is skipped and only morphological properties (centroids) are saved.
    When a channel has thresholds enabled, thresholded columns are emitted
    with a ``_thresholded`` suffix while the unthresholded values are kept.
    """
    data = feature.data
    if not isinstance(data, MarkerFeatureData) or viewer is None:
        return []

    export_format = (export_format or "csv").lower()
    outputs: list[Path] = []
    channels = [channel for channel in data.channels if channel.channel]
    if not data.segmentations or not channels:
        return []

    if enable_thresholds:
        metadata_path = _write_threshold_metadata(temp_dir, channels)
        if metadata_path is not None:
            outputs.append(metadata_path)

    for index, segmentation in enumerate(data.segmentations, start=0):
        label_name = segmentation.label.strip()
        if not label_name:
            continue
        labels_layer = _find_layer(viewer, label_name, "Labels")
        if labels_layer is None:
            continue
        labels = layer_data_asarray(labels_layer)
        if labels.size == 0:
            continue

        label_ids, centroids = _compute_centroids(labels)
        if label_ids.size == 0:
            continue
        area_px = _pixel_counts(labels, label_ids)

        pixel_sizes = _pixel_sizes(labels_layer, labels.ndim)
        if pixel_sizes is None:
            for channel in channels:
                channel_layer = _find_layer(viewer, channel.channel, "Image")
                if channel_layer is None:
                    continue
                pixel_sizes = _pixel_sizes(channel_layer, labels.ndim)
                if pixel_sizes is not None:
                    break
        rows = _initialize_rows(label_ids, centroids, pixel_sizes)
        _add_roi_columns(rows, labels, label_ids, viewer, data.rois, label_name)
        morph_columns = add_morphology_columns(
            rows, labels, label_ids, pixel_sizes
        )
        
        # Extract file path from metadata if available
        file_path = None
        if channels:
            first_channel_layer = _find_layer(viewer, channels[0].channel, "Image")
            if first_channel_layer is not None:
                metadata = getattr(first_channel_layer, "metadata", {})
                file_path = metadata.get("path")
        
        # Determine segmentation type from label name or config
        seg_type = getattr(segmentation, "task", "nuclear")
        ref_columns = _add_reference_columns(
            rows, labels, label_ids, file_path, seg_type
        )
        
        header = list(rows[0].keys()) if rows else []

        for channel in channels:
            channel_layer = _find_layer(viewer, channel.channel, "Image")
            if channel_layer is None:
                continue
            image = layer_data_asarray(channel_layer)
            if image.shape != labels.shape:
                warnings.warn(
                    "Marker export: image/label shape mismatch for "
                    f"'{channel.channel}' vs '{label_name}'. "
                    "Skipping intensity metrics for this channel; "
                    "only morphological properties will be saved.",
                    RuntimeWarning,
                )
                continue
            raw_sum = _intensity_sum(labels, image, label_ids)
            mean_intensity = _safe_divide(raw_sum, area_px)
            pixel_volume = _pixel_volume(channel_layer, labels.ndim)
            integrated = mean_intensity * (area_px * pixel_volume)
            if enable_thresholds:
                thresh_mean, thresh_raw, thresh_integrated = _apply_threshold(
                    mean_intensity,
                    raw_sum,
                    integrated,
                    channel,
                )
            else:
                thresh_mean, thresh_raw, thresh_integrated = (
                    mean_intensity,
                    raw_sum,
                    integrated,
                )
            prefix = _channel_prefix(channel)
            for row, mean_val, raw_val, int_val in zip(
                rows, mean_intensity, raw_sum, integrated
            ):
                row[f"{prefix}_mean_intensity"] = float(mean_val)
                row[f"{prefix}_integrated_intensity"] = float(int_val)
                row[f"{prefix}_raw_integrated_intensity"] = float(raw_val)
            if enable_thresholds and getattr(channel, "threshold_enabled", False):
                for row, mean_val, raw_val, int_val in zip(
                    rows, thresh_mean, thresh_raw, thresh_integrated
                ):
                    row[f"{prefix}_mean_intensity_thresholded"] = float(mean_val)
                    row[f"{prefix}_integrated_intensity_thresholded"] = float(
                        int_val
                    )
                    row[f"{prefix}_raw_integrated_intensity_thresholded"] = float(
                        raw_val
                    )
            if not header:
                header = list(rows[0].keys())
            else:
                header.extend(
                    [
                        f"{prefix}_mean_intensity",
                        f"{prefix}_integrated_intensity",
                        f"{prefix}_raw_integrated_intensity",
                    ]
                )
                if enable_thresholds and getattr(channel, "threshold_enabled", False):
                    header.extend(
                        [
                            f"{prefix}_mean_intensity_thresholded",
                            f"{prefix}_integrated_intensity_thresholded",
                            f"{prefix}_raw_integrated_intensity_thresholded",
                        ]
                    )

        if not rows:
            continue
        file_stem = _sanitize_name(label_name or f"segmentation_{index}")
        output_path = temp_dir / f"{file_stem}.{export_format}"
        _write_table(output_path, header, rows, export_format)
        outputs.append(output_path)

    return outputs


def _find_layer(viewer, name: str, layer_type: str):
    """Return a layer by name and class name.

    Parameters
    ----------
    viewer : object
        Napari viewer instance containing layers.
    name : str
        Layer name to locate.
    layer_type : str
        Layer class name to match (e.g., ``"Image"`` or ``"Labels"``).

    Returns
    -------
    object or None
        Matching layer instance, or ``None`` if not found.
    """
    for layer in viewer.layers:
        if layer.__class__.__name__ == layer_type and layer.name == name:
            return layer
    return None


def _compute_centroids(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute centroid coordinates for each non-zero label.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image with integer ids.

    Returns
    -------
    tuple of numpy.ndarray
        Label ids and centroid coordinates in pixel units.
    """
    props = regionprops_table(labels, properties=("label", "centroid"))
    label_ids = np.asarray(props.get("label", []), dtype=int)
    centroid_cols = [key for key in props if key.startswith("centroid-")]
    if not centroid_cols:
        return label_ids, np.empty((0, labels.ndim), dtype=float)
    centroids = np.column_stack([props[key] for key in centroid_cols]).astype(float)
    return label_ids, centroids


def _pixel_counts(labels: np.ndarray, label_ids: np.ndarray) -> np.ndarray:
    """Return pixel counts for each label id.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image with integer ids.
    label_ids : numpy.ndarray
        Label ids to extract counts for.

    Returns
    -------
    numpy.ndarray
        Pixel counts for each provided label id.
    """
    labels_flat = labels.ravel()
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    counts = np.bincount(labels_flat, minlength=max_label + 1)
    return counts[label_ids]


def _intensity_sum(
    labels: np.ndarray, image: np.ndarray, label_ids: np.ndarray
) -> np.ndarray:
    """Return raw intensity sums for each label id.

    Parameters
    ----------
    labels : numpy.ndarray
        Label image with integer ids.
    image : numpy.ndarray
        Image data aligned to ``labels``.
    label_ids : numpy.ndarray
        Label ids to extract sums for.

    Returns
    -------
    numpy.ndarray
        Raw intensity sums for each label id.
    """
    labels_flat = labels.ravel()
    image_flat = np.nan_to_num(image.ravel(), nan=0.0)
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    sums = np.bincount(labels_flat, weights=image_flat, minlength=max_label + 1)
    return sums[label_ids]


def _pixel_volume(layer, ndim: int) -> float:
    """Compute per-pixel physical volume from layer metadata.

    Parameters
    ----------
    layer : object
        Napari image layer providing metadata.
    ndim : int
        Dimensionality of the image data.

    Returns
    -------
    float
        Physical volume of one pixel/voxel in cubic micrometers.

    Notes
    -----
    The SenoQuant reader stores physical sizes under
    ``layer.metadata["physical_pixel_sizes"]`` with keys ``"Z"``, ``"Y"``,
    and ``"X"`` in micrometers (um). Missing values default to 1.0 so the
    measurement stays in pixel units.
    """
    pixel_sizes = _pixel_sizes(layer, ndim)
    if pixel_sizes is None:
        return 1.0
    return float(np.prod(pixel_sizes))


def _safe_float(value) -> float | None:
    """Convert a metadata value to float when possible.

    Parameters
    ----------
    value : object
        Metadata value to convert.

    Returns
    -------
    float or None
        Converted value when possible, otherwise ``None``.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pixel_sizes(layer, ndim: int) -> np.ndarray | None:
    """Return per-axis pixel sizes from layer metadata.

    Parameters
    ----------
    layer : object
        Napari image layer providing metadata.
    ndim : int
        Dimensionality of the image data.

    Returns
    -------
    numpy.ndarray or None
        Per-axis pixel sizes in micrometers, ordered to match the data axes.

    Notes
    -----
    For 2D images the Z size may be ``None`` and is ignored.
    """
    metadata = getattr(layer, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    physical_sizes = metadata.get("physical_pixel_sizes")
    if not isinstance(physical_sizes, dict):
        return None
    size_x = physical_sizes.get("X")
    size_y = physical_sizes.get("Y")
    size_z = physical_sizes.get("Z")
    return _pixel_sizes_from_metadata(size_x, size_y, size_z, ndim)


def _pixel_sizes_from_metadata(
    size_x, size_y, size_z, ndim: int
) -> np.ndarray | None:
    """Normalize metadata sizes into axis-ordered pixel sizes.

    Parameters
    ----------
    size_x : object
        Physical size along X.
    size_y : object
        Physical size along Y.
    size_z : object
        Physical size along Z.
    ndim : int
        Dimensionality of the image data.

    Returns
    -------
    numpy.ndarray or None
        Axis-ordered pixel sizes in micrometers.
    """
    axis_sizes = {
        "x": _safe_float(size_x),
        "y": _safe_float(size_y),
        "z": _safe_float(size_z),
    }
    if ndim == 2:
        sizes = [axis_sizes["y"], axis_sizes["x"]]
    elif ndim == 3:
        sizes = [axis_sizes["z"], axis_sizes["y"], axis_sizes["x"]]
    else:
        return None
    if any(value is None for value in sizes):
        return None
    return np.asarray(sizes, dtype=float)


def _add_roi_columns(
    rows: list[dict[str, float]],
    labels: np.ndarray,
    label_ids: np.ndarray,
    viewer: object | None,
    rois: Sequence["ROIConfig"],
    label_name: str,
) -> None:
    """Add per-ROI inclusion columns to the output rows.

    Parameters
    ----------
    rows : list of dict
        Output row dictionaries to update in-place.
    labels : numpy.ndarray
        Label image used to compute ROI intersections.
    label_ids : numpy.ndarray
        Label ids corresponding to the output rows.
    viewer : object or None
        Napari viewer used to resolve shapes layers.
    rois : sequence of ROIConfig
        ROI configuration entries to evaluate.
    label_name : str
        Name of the labels layer (for warnings).
    """
    if viewer is None or not rois or not rows:
        return
    labels_flat = labels.ravel()
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    for index, roi in enumerate(rois, start=0):
        layer_name = getattr(roi, "layer", "")
        if not layer_name:
            continue
        shapes_layer = _find_layer(viewer, layer_name, "Shapes")
        if shapes_layer is None:
            warnings.warn(
                f"ROI layer '{layer_name}' not found for labels '{label_name}'.",
                RuntimeWarning,
            )
            continue
        mask = _shapes_layer_mask(shapes_layer, labels.shape)
        if mask is None:
            warnings.warn(
                f"ROI layer '{layer_name}' could not be rasterized.",
                RuntimeWarning,
            )
            continue
        intersect_counts = np.bincount(
            labels_flat[mask.ravel()], minlength=max_label + 1
        )
        included = intersect_counts[label_ids] > 0
        roi_name = getattr(roi, "name", "") or f"roi_{index}"
        roi_type = getattr(roi, "roi_type", "Include") or "Include"
        if roi_type.lower() == "exclude":
            prefix = "excluded_from_roi"
        else:
            prefix = "included_in_roi"
        column = f"{prefix}_{_sanitize_name(roi_name)}"
        for row, value in zip(rows, included):
            row[column] = int(value)


def _shapes_layer_mask(
    layer: object, shape: tuple[int, ...]
) -> np.ndarray | None:
    """Render a shapes layer into a boolean mask.

    Parameters
    ----------
    layer : object
        Napari shapes layer instance.
    shape : tuple of int
        Target mask shape matching the labels array.

    Returns
    -------
    numpy.ndarray or None
        Boolean mask array when rendering succeeds.
    """
    masks_array = _shape_masks_array(layer, shape)
    if masks_array is None:
        return None
    if masks_array.ndim == len(shape):
        combined = masks_array
    else:
        combined = np.any(masks_array, axis=0)
    combined = np.asarray(combined)
    combined = np.squeeze(combined)
    if combined.shape != shape:
        return None
    return combined.astype(bool)


def _shape_masks_array(
    layer: object, shape: tuple[int, ...]
) -> np.ndarray | None:
    """Return the raw masks array from a shapes layer."""
    to_masks = getattr(layer, "to_masks", None)
    if callable(to_masks):
        try:
            return np.asarray(to_masks(mask_shape=shape))
        except Exception:
            return None
    return None


def _axis_names(ndim: int) -> list[str]:
    """Return axis suffixes for centroid columns.

    Parameters
    ----------
    ndim : int
        Number of spatial dimensions.

    Returns
    -------
    list of str
        Axis suffixes in display order.
    """
    if ndim == 2:
        return ["y", "x"]
    if ndim == 3:
        return ["z", "y", "x"]
    return [f"axis_{idx}" for idx in range(ndim)]


def _initialize_rows(
    label_ids: np.ndarray,
    centroids: np.ndarray,
    pixel_sizes: np.ndarray | None,
) -> list[dict[str, float]]:
    """Initialize output rows with label ids and centroid coordinates.

    Parameters
    ----------
    label_ids : numpy.ndarray
        Label identifiers for each row.
    centroids : numpy.ndarray
        Centroid coordinates in pixel units.
    pixel_sizes : numpy.ndarray or None
        Per-axis pixel sizes in micrometers.

    Returns
    -------
    list of dict
        Row dictionaries with centroid fields populated.
    """
    axes = _axis_names(centroids.shape[1] if centroids.size else 0)
    rows: list[dict[str, float]] = []
    for label_id, centroid in zip(label_ids, centroids):
        row: dict[str, float] = {"label_id": int(label_id)}
        for axis, value in zip(axes, centroid):
            row[f"centroid_{axis}_pixels"] = float(value)
        if pixel_sizes is not None and pixel_sizes.size == len(axes):
            for axis, value, scale in zip(axes, centroid, pixel_sizes):
                row[f"centroid_{axis}_um"] = float(value * scale)
        rows.append(row)
    return rows


def _channel_prefix(channel) -> str:
    """Return a sanitized column prefix for a channel.

    Parameters
    ----------
    channel : object
        Marker channel configuration.

    Returns
    -------
    str
        Sanitized prefix for column names.
    """
    name = channel.name.strip() if channel.name else ""
    if not name:
        name = channel.channel
    return _sanitize_name(name)


def _sanitize_name(value: str) -> str:
    """Normalize names for filenames and column prefixes.

    Parameters
    ----------
    value : str
        Raw name to sanitize.

    Returns
    -------
    str
        Lowercased name with unsafe characters removed.
    """
    cleaned = "".join(
        char if char.isalnum() or char in "-_ " else "_" for char in value
    )
    return cleaned.strip().replace(" ", "_").lower()


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Compute numerator/denominator with zero-safe handling.

    Parameters
    ----------
    numerator : numpy.ndarray
        Numerator values.
    denominator : numpy.ndarray
        Denominator values.

    Returns
    -------
    numpy.ndarray
        Division result with zero denominators handled safely.
    """
    result = np.zeros_like(numerator, dtype=float)
    np.divide(
        numerator,
        denominator,
        out=result,
        where=denominator != 0,
    )
    return result


def _apply_threshold(
    mean_intensity: np.ndarray,
    raw_sum: np.ndarray,
    integrated: np.ndarray,
    channel,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zero intensity values outside the configured threshold range.

    Parameters
    ----------
    mean_intensity : np.ndarray
        Mean intensity per label.
    raw_sum : np.ndarray
        Raw integrated intensity per label.
    integrated : np.ndarray
        Physical-unit integrated intensity per label.
    channel : object
        Channel configuration with threshold metadata.

    Returns
    -------
    tuple of numpy.ndarray
        Thresholded mean, raw, and integrated intensity arrays.
    """
    if not getattr(channel, "threshold_enabled", False):
        return mean_intensity, raw_sum, integrated
    min_val = getattr(channel, "threshold_min", None)
    max_val = getattr(channel, "threshold_max", None)
    keep = np.ones_like(mean_intensity, dtype=bool)
    if min_val is not None:
        keep &= mean_intensity >= float(min_val)
    if max_val is not None:
        keep &= mean_intensity <= float(max_val)
    if keep.all():
        return mean_intensity, raw_sum, integrated
    mean = mean_intensity.copy()
    raw = raw_sum.copy()
    integ = integrated.copy()
    mean[~keep] = 0.0
    raw[~keep] = 0.0
    integ[~keep] = 0.0
    return mean, raw, integ


def _write_threshold_metadata(
    temp_dir: Path, channels: list
) -> Optional[Path]:
    """Persist channel threshold metadata for the export run.

    Parameters
    ----------
    temp_dir : Path
        Temporary output directory.
    channels : list
        Channel configurations to serialize.

    Returns
    -------
    pathlib.Path or None
        Path to the metadata file written.
    """
    payload = {
        "channels": [
            {
                "name": channel.name,
                "channel": channel.channel,
                "threshold_enabled": bool(channel.threshold_enabled),
                "threshold_method": channel.threshold_method,
                "threshold_min": channel.threshold_min,
                "threshold_max": channel.threshold_max,
            }
            for channel in channels
        ]
    }
    output_path = temp_dir / "marker_thresholds.json"
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return output_path


def _add_reference_columns(
    rows: list[dict],
    labels: np.ndarray,
    label_ids: np.ndarray,
    file_path: str | None,
    segmentation_type: str,
) -> list[str]:
    """Add reference columns to marker export rows.

    Parameters
    ----------
    rows : list of dict
        Output row dictionaries to update in-place.
    labels : numpy.ndarray
        Label image with integer ids.
    label_ids : numpy.ndarray
        Label ids corresponding to the output rows.
    file_path : str or None
        Original file path from metadata.
    segmentation_type : str
        Type of segmentation ("nuclear" or "cytoplasmic").

    Returns
    -------
    list of str
        List of column names added.
    """
    column_names: list[str] = []

    # Add file path column
    if file_path:
        for row in rows:
            row["file_path"] = str(file_path)
        column_names.append("file_path")

    # Add segmentation type column
    for row in rows:
        row["segmentation_type"] = segmentation_type
    column_names.append("segmentation_type")

    return column_names


def _build_cross_segmentation_map(
    all_segmentations: dict[str, tuple[np.ndarray, np.ndarray]],
) -> dict[tuple[str, int], list[tuple[str, int]]]:
    """Build a mapping of label overlaps across segmentations.

    Parameters
    ----------
    all_segmentations : dict
        Mapping from segmentation name to (labels, label_ids) tuple.

    Returns
    -------
    dict
        Mapping from (seg_name, label_id) to list of overlapping
        (other_seg_name, overlapping_label_id) tuples.

    Notes
    -----
    This function identifies which labels from different segmentations
    overlap spatially, enabling cross-referencing between tables.
    """
    cross_map: dict[tuple[str, int], list[tuple[str, int]]] = {}

    seg_names = list(all_segmentations.keys())
    for i, seg1_name in enumerate(seg_names):
        labels1, label_ids1 = all_segmentations[seg1_name]
        for label_id1 in label_ids1:
            cross_map[(seg1_name, int(label_id1))] = []
            # Check overlaps with all other segmentations
            for seg2_name in seg_names[i + 1 :]:
                labels2, _label_ids2 = all_segmentations[seg2_name]
                # Find which labels in seg2 overlap with label_id1
                mask1 = labels1 == label_id1
                overlapping_labels2 = np.unique(labels2[mask1])
                overlapping_labels2 = overlapping_labels2[overlapping_labels2 > 0]
                for label_id2 in overlapping_labels2:
                    cross_map[(seg1_name, int(label_id1))].append(
                        (seg2_name, int(label_id2)),
                    )

    return cross_map


def _add_cross_reference_column(
    rows: list[dict],
    segmentation_name: str,
    label_ids: np.ndarray,
    cross_map: dict,
) -> str:
    """Add a cross-reference column to rows for multi-segmentation overlaps.

    Parameters
    ----------
    rows : list of dict
        Output row dictionaries to update in-place.
    segmentation_name : str
        Name of this segmentation.
    label_ids : numpy.ndarray
        Label ids corresponding to the output rows.
    cross_map : dict
        Cross-segmentation overlap mapping from _build_cross_segmentation_map.

    Returns
    -------
    str
        Column name added.
    """
    for row, label_id in zip(rows, label_ids, strict=True):
        overlaps = cross_map.get((segmentation_name, int(label_id)), [])
        if overlaps:
            overlap_str = ";".join(
                [f"{seg}_{lid}" for seg, lid in overlaps],
            )
            row["overlaps_with"] = overlap_str
        else:
            row["overlaps_with"] = ""

    return "overlaps_with"




def _write_table(
    path: Path, header: list[str], rows: list[dict[str, float]], fmt: str
) -> None:
    """Write rows to disk as CSV or XLSX.

    Parameters
    ----------
    path : pathlib.Path
        Destination file path.
    header : list of str
        Column names for the output table.
    rows : list of dict
        Table rows keyed by column name.
    fmt : str
        Output format (``"csv"`` or ``"xlsx"``).
    """
    if fmt == "csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        return

    if fmt == "xlsx":
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openpyxl is required for xlsx export"
            ) from exc
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(header)
        for row in rows:
            sheet.append([row.get(column) for column in header])
        workbook.save(path)
        return

    raise ValueError(f"Unsupported export format: {fmt}")
