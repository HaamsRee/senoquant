"""Spots feature export logic.

This module produces two export tables for every configured nuclear or
cytoplasmic segmentation:

1. A **cells** table with morphology, ROI membership, and per-channel
   spot summaries (counts and mean spot intensity per cell).
2. A **spots** table with per-spot geometry, ROI membership, and the
   channel the spot belongs to.

The export matches the markers feature style for morphology and physical
unit reporting. If physical pixel sizes are available in the metadata for
the first configured channel image, both pixel and physical units are
saved for centroids and areas/volumes.
"""

from __future__ import annotations

import csv
import warnings
from pathlib import Path
from typing import Iterable, Sequence, TYPE_CHECKING

import numpy as np
from skimage.measure import regionprops_table

from senoquant.utils import layer_data_asarray
from .config import SpotsFeatureData
from ..base import FeatureConfig
from .morphology import add_morphology_columns

if TYPE_CHECKING:
    from ..roi import ROIConfig


def export_spots(
    feature: FeatureConfig,
    temp_dir: Path,
    viewer=None,
    export_format: str = "csv",
) -> Iterable[Path]:
    """Export spots feature outputs into a temporary directory.

    Parameters
    ----------
    feature : FeatureConfig
        Spots feature configuration to export. Must contain a
        :class:`SpotsFeatureData` payload with at least one segmentation
        and one channel.
    temp_dir : Path
        Temporary directory where outputs should be written.
    viewer : object, optional
        Napari viewer instance used to resolve layers by name and read
        layer data. When ``None``, export is skipped.
    export_format : str, optional
        File format for exports (``"csv"`` or ``"xlsx"``). Values are
        normalized to lower case.

    Returns
    -------
    iterable of Path
        Paths to files produced by the export routine. Each segmentation
        produces two tables: ``*_cells`` and ``*_spots``. If no outputs
        are produced, an empty list is returned.

    Notes
    -----
    - Cell morphology comes from the segmentation labels.
    - Spot-to-cell assignment is based on the spot centroid location.
    - Spot intensities are computed from the channel image referenced by
      each channel config. Missing or mismatched images result in ``NaN``
      mean intensities for those spots.
    - When ``export_colocalization`` is enabled on the feature, additional
      colocalization columns are appended to both tables.
    - Physical units are derived from ``layer.metadata["physical_pixel_sizes"]``
      when available (same convention as the markers export).

    Workflow summary
    ----------------
    1. Resolve the requested cell segmentation and compute cell morphology.
    2. Build per-channel spot exports (counts, mean intensity, spot rows).
    3. Optionally compute colocalization adjacency and append columns.
    4. Write ``*_cells`` and ``*_spots`` outputs for each segmentation.
    """
    data = feature.data
    if not isinstance(data, SpotsFeatureData) or viewer is None:
        return []

    # --- Normalize inputs and pre-filter channel configs ---
    export_format = (export_format or "csv").lower()
    outputs: list[Path] = []
    channels = [
        channel
        for channel in data.channels
        if channel.channel and channel.spots_segmentation
    ]
    # Require both segmentations and channels to export anything.
    if not data.segmentations or not channels:
        return []

    # --- Resolve a reference channel for physical pixel sizes ---
    first_channel_layer = None
    for channel in channels:
        first_channel_layer = _find_layer(viewer, channel.channel, "Image")
        if first_channel_layer is not None:
            break

    for index, segmentation in enumerate(data.segmentations, start=0):
        # --- Resolve the cell segmentation labels layer ---
        label_name = segmentation.label.strip()
        if not label_name:
            continue
        labels_layer = _find_layer(viewer, label_name, "Labels")
        if labels_layer is None:
            continue
        cell_labels = layer_data_asarray(labels_layer)
        if cell_labels.size == 0:
            continue

        # --- Compute per-cell morphology from the segmentation ---
        cell_ids, cell_centroids = _compute_centroids(cell_labels)
        if cell_ids.size == 0:
            continue

        # --- Derive physical pixel sizes from metadata if available ---
        cell_pixel_sizes = _pixel_sizes(labels_layer, cell_labels.ndim)
        if cell_pixel_sizes is None and first_channel_layer is not None:
            cell_pixel_sizes = _pixel_sizes(
                first_channel_layer, cell_labels.ndim
            )

        # --- Seed the cell table with morphology and ROI membership columns ---
        cell_rows = _initialize_rows(
            cell_ids, cell_centroids, cell_pixel_sizes
        )
        
        # --- Add morphological descriptors to the cell table ---
        add_morphology_columns(cell_rows, cell_labels, cell_ids, cell_pixel_sizes)
        
        _add_roi_columns(
            cell_rows,
            cell_labels,
            cell_ids,
            viewer,
            data.rois,
            label_name,
        )
        cell_header = list(cell_rows[0].keys()) if cell_rows else []

        # --- Prepare containers and ROI masks for the spots table ---
        spot_rows: list[dict[str, object]] = []
        spot_header: list[str] = []
        spot_table_pixel_sizes = None
        if first_channel_layer is not None:
            spot_table_pixel_sizes = _pixel_sizes(
                first_channel_layer, cell_labels.ndim
            )
        spot_roi_columns = _spot_roi_columns(
            viewer, data.rois, label_name, cell_labels.shape
        )

        # --- Resolve per-channel label layers before heavy computation ---
        channel_entries = _build_channel_entries(
            viewer, channels, cell_labels.shape, label_name
        )
        adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
        if data.export_colocalization and len(channel_entries) >= 2:
            adjacency = _build_colocalization_adjacency(channel_entries)

        # --- Compute per-channel cell metrics + per-spot rows ---
        spot_lookup: dict[tuple[int, int], dict[str, object]] = {}
        for channel_index, entry in enumerate(channel_entries):
            _append_channel_exports(
                channel_index,
                entry,
                cell_labels,
                cell_ids,
                cell_header,
                cell_rows,
                spot_rows,
                spot_header,
                spot_lookup,
                spot_table_pixel_sizes,
                spot_roi_columns,
            )

        # --- Apply colocalization columns (if requested) ---
        if data.export_colocalization:
            _apply_colocalization_columns(
                cell_rows,
                cell_ids,
                cell_header,
                spot_rows,
                spot_lookup,
                adjacency,
                channel_entries,
                int(cell_labels.max()),
            )

        # --- Emit cells and spots tables for the segmentation ---
        file_stem = _sanitize_name(label_name or f"segmentation_{index}")
        if cell_rows:
            cell_path = temp_dir / f"{file_stem}_cells.{export_format}"
            _write_table(cell_path, cell_header, cell_rows, export_format)
            outputs.append(cell_path)
        if not spot_header:
            spot_header = _spot_header(
                cell_labels.ndim, spot_table_pixel_sizes, spot_roi_columns
            )
        if data.export_colocalization:
            if "colocalizes_with" not in spot_header:
                spot_header.append("colocalizes_with")
            for row in spot_rows:
                row.setdefault("colocalizes_with", "")
        spot_path = temp_dir / f"{file_stem}_spots.{export_format}"
        _write_table(spot_path, spot_header, spot_rows, export_format)
        outputs.append(spot_path)

    return outputs


def _build_channel_entries(
    viewer: object,
    channels: list,
    cell_shape: tuple[int, ...],
    label_name: str,
) -> list[dict[str, object]]:
    """Resolve channel layers into export-ready entries.

    Parameters
    ----------
    viewer : object
        Napari viewer instance used to resolve layers.
    channels : list
        Spots channel configurations (image + labels names).
    cell_shape : tuple of int
        Shape of the cell segmentation labels for validation.
    label_name : str
        Cell labels layer name (for warning context).

    Returns
    -------
    list of dict
        Each entry includes:
        - ``channel_label`` : str
            Display label for the channel.
        - ``channel_layer`` : object or None
            Image layer for intensity calculation.
        - ``spots_labels`` : numpy.ndarray
            Spots segmentation labels aligned to ``cell_shape``.

    Notes
    -----
    Channels are filtered out when their segmentation layer is missing or
    the segmentation does not match the cell labels shape.
    """
    entries: list[dict[str, object]] = []
    for channel in channels:
        # Resolve channel display label and layer references.
        channel_label = _channel_label(channel)
        channel_layer = _find_layer(viewer, channel.channel, "Image")
        spots_layer = _find_layer(viewer, channel.spots_segmentation, "Labels")
        if spots_layer is None:
            warnings.warn(
                "Spots export: spots segmentation layer "
                f"'{channel.spots_segmentation}' not found.",
                RuntimeWarning,
            )
            continue
        spots_labels = layer_data_asarray(spots_layer)
        if spots_labels.shape != cell_shape:
            warnings.warn(
                "Spots export: segmentation shape mismatch for "
                f"'{label_name}' vs '{channel.spots_segmentation}'. "
                "Skipping this channel for the segmentation.",
                RuntimeWarning,
            )
            continue
        entries.append(
            {
                "channel_label": channel_label,
                "channel_layer": channel_layer,
                "spots_labels": spots_labels,
            }
        )
    return entries


def _append_channel_exports(
    channel_index: int,
    entry: dict[str, object],
    cell_labels: np.ndarray,
    cell_ids: np.ndarray,
    cell_header: list[str],
    cell_rows: list[dict[str, object]],
    spot_rows: list[dict[str, object]],
    spot_header: list[str],
    spot_lookup: dict[tuple[int, int], dict[str, object]],
    spot_table_pixel_sizes: np.ndarray | None,
    spot_roi_columns: list[tuple[str, np.ndarray]],
) -> None:
    """Compute and append per-channel cell/spot metrics.

    Parameters
    ----------
    channel_index : int
        Index of the channel in the resolved channel list.
    entry : dict
        Channel entry from :func:`_build_channel_entries`.
    cell_labels : numpy.ndarray
        Cell segmentation labels array.
    cell_ids : numpy.ndarray
        Cell ids derived from the segmentation.
    cell_header : list of str
        Header list for the cells table, updated in-place.
    cell_rows : list of dict
        Cell rows updated in-place.
    spot_rows : list of dict
        Spot rows appended to in-place.
    spot_header : list of str
        Spot header list updated in-place.
    spot_lookup : dict
        Mapping from ``(channel_index, spot_id)`` to row metadata.
    spot_table_pixel_sizes : numpy.ndarray or None
        Pixel sizes to use for spot physical units.
    spot_roi_columns : list of tuple
        ROI masks for spot ROI membership columns.
    """
    channel_label = entry["channel_label"]
    channel_layer = entry["channel_layer"]
    spots_labels = entry["spots_labels"]

    # Compute spot centroids in the channel segmentation.
    spot_ids, spot_centroids = _compute_centroids(spots_labels)
    if spot_ids.size == 0:
        # No spots -> still emit per-cell count/mean columns with zeros/nans.
        _append_cell_metrics(
            cell_rows,
            np.zeros_like(cell_ids, dtype=int),
            np.full_like(cell_ids, np.nan, dtype=float),
            channel_label,
            cell_header,
        )
        return

    # Spot areas (pixels) and mean intensity (per spot).
    spot_area_px = _pixel_counts(spots_labels, spot_ids)
    spot_mean_intensity = None
    if channel_layer is not None:
        image = layer_data_asarray(channel_layer)
        if image.shape != spots_labels.shape:
            warnings.warn(
                "Spots export: image/spot shape mismatch for "
                f"'{channel_label}'. Spot intensity values will be empty.",
                RuntimeWarning,
            )
        else:
            raw_sum = _intensity_sum(spots_labels, image, spot_ids)
            spot_mean_intensity = _safe_divide(raw_sum, spot_area_px)
    if spot_mean_intensity is None:
        spot_mean_intensity = np.full(spot_area_px.shape, np.nan, dtype=float)

    # Assign spots to cells using the centroid location.
    cell_ids_for_spots = _spot_cell_ids_from_centroids(
        cell_labels, spot_centroids
    )
    valid_mask = cell_ids_for_spots > 0
    valid_cell_ids = cell_ids_for_spots[valid_mask]
    valid_spot_ids = spot_ids[valid_mask]
    valid_centroids = spot_centroids[valid_mask]
    valid_areas = spot_area_px[valid_mask]
    valid_means = spot_mean_intensity[valid_mask]

    # Aggregate per-cell metrics and append columns to the cell table.
    cell_counts, cell_means = _cell_spot_metrics(
        valid_cell_ids, valid_means, int(cell_labels.max())
    )
    _append_cell_metrics(
        cell_rows,
        cell_counts[cell_ids],
        cell_means[cell_ids],
        channel_label,
        cell_header,
    )

    # Append per-spot rows for this channel, preserving ROI membership.
    spot_rows_for_channel = _spot_rows(
        valid_spot_ids,
        valid_cell_ids,
        valid_centroids,
        valid_areas,
        valid_means,
        channel_label,
        spot_table_pixel_sizes,
        spot_roi_columns,
    )
    if spot_rows_for_channel:
        if not spot_header:
            spot_header.extend(list(spot_rows_for_channel[0].keys()))
        for row, spot_id, cell_id in zip(
            spot_rows_for_channel, valid_spot_ids, valid_cell_ids
        ):
            spot_lookup[(channel_index, int(spot_id))] = {
                "row": row,
                "cell_id": int(cell_id),
            }
        spot_rows.extend(spot_rows_for_channel)


def _build_colocalization_adjacency(
    channel_entries: list[dict[str, object]]
) -> dict[tuple[int, int], set[tuple[int, int]]]:
    """Build adjacency between overlapping spots across channels.

    Parameters
    ----------
    channel_entries : list of dict
        Channel entries with ``spots_labels`` arrays.

    Returns
    -------
    dict
        Mapping of ``(channel_index, spot_id)`` to a set of overlapping
        ``(channel_index, spot_id)`` pairs.

    Notes
    -----
    Two spots are considered colocalized when their label masks overlap.
    """
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for idx_a, entry_a in enumerate(channel_entries):
        labels_a = entry_a["spots_labels"]
        for idx_b in range(idx_a + 1, len(channel_entries)):
            labels_b = channel_entries[idx_b]["spots_labels"]
            mask = (labels_a > 0) & (labels_b > 0)
            if not np.any(mask):
                continue
            pairs = np.column_stack((labels_a[mask], labels_b[mask]))
            unique_pairs = np.unique(pairs, axis=0)
            for spot_a, spot_b in unique_pairs:
                key_a = (idx_a, int(spot_a))
                key_b = (idx_b, int(spot_b))
                adjacency.setdefault(key_a, set()).add(key_b)
                adjacency.setdefault(key_b, set()).add(key_a)
    return adjacency


def _apply_colocalization_columns(
    cell_rows: list[dict[str, object]],
    cell_ids: np.ndarray,
    cell_header: list[str],
    spot_rows: list[dict[str, object]],
    spot_lookup: dict[tuple[int, int], dict[str, object]],
    adjacency: dict[tuple[int, int], set[tuple[int, int]]],
    channel_entries: list[dict[str, object]],
    max_cell_id: int,
) -> None:
    """Append colocalization columns to cell and spot rows.

    Parameters
    ----------
    cell_rows : list of dict
        Cell rows updated in-place.
    cell_ids : numpy.ndarray
        Cell id array aligned to ``cell_rows``.
    cell_header : list of str
        Cell header updated in-place.
    spot_rows : list of dict
        Spot rows updated in-place.
    spot_lookup : dict
        Mapping from ``(channel_index, spot_id)`` to spot row and cell id.
    adjacency : dict
        Colocalization adjacency built by
        :func:`_build_colocalization_adjacency`.
    channel_entries : list of dict
        Channel entries used to map channel indices to labels.
    max_cell_id : int
        Maximum cell id in the segmentation, used to size count arrays.

    Notes
    -----
    ``colocalizes_with`` is a semicolon-delimited list of
    ``"<channel_label>:<spot_id>"`` entries.
    ``colocalization_event_count`` counts unique overlapping spot pairs
    within the same cell.
    """
    channel_labels = [entry["channel_label"] for entry in channel_entries]
    for key, info in spot_lookup.items():
        others = adjacency.get(key, set())
        names: list[str] = []
        for other in others:
            if other not in spot_lookup:
                continue
            other_label = channel_labels[other[0]]
            names.append(f"{other_label}:{other[1]}")
        info["row"]["colocalizes_with"] = (
            ";".join(sorted(set(names))) if names else ""
        )
    for row in spot_rows:
        row.setdefault("colocalizes_with", "")

    colocalization_key = "colocalization_event_count"
    event_counts = np.zeros(max_cell_id + 1, dtype=int)
    seen_pairs: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for key, others in adjacency.items():
        if key not in spot_lookup:
            continue
        for other in others:
            if other not in spot_lookup:
                continue
            pair = (key, other) if key < other else (other, key)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            cell_id_a = spot_lookup[key]["cell_id"]
            cell_id_b = spot_lookup[other]["cell_id"]
            if cell_id_a > 0 and cell_id_a == cell_id_b:
                event_counts[cell_id_a] += 1
    for row, cell_id in zip(cell_rows, cell_ids):
        row[colocalization_key] = int(event_counts[cell_id])
    if colocalization_key not in cell_header:
        cell_header.append(colocalization_key)


def _find_layer(viewer, name: str, layer_type: str):
    """Return a viewer layer by name and class name.

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
        Integer label image. ``0`` is treated as background.

    Returns
    -------
    tuple of numpy.ndarray
        ``(label_ids, centroids)`` where ``label_ids`` is a 1D array of
        label ids and ``centroids`` is an ``(N, D)`` array of centroid
        coordinates in pixel units.
    """
    props = regionprops_table(labels, properties=("label", "centroid"))
    label_ids = np.asarray(props.get("label", []), dtype=int)
    centroid_cols = [key for key in props if key.startswith("centroid-")]
    if not centroid_cols:
        return label_ids, np.empty((0, labels.ndim), dtype=float)
    centroids = np.column_stack([props[key] for key in centroid_cols]).astype(
        float
    )
    return label_ids, centroids


def _pixel_counts(labels: np.ndarray, label_ids: np.ndarray) -> np.ndarray:
    """Return pixel counts for each label id.

    Parameters
    ----------
    labels : numpy.ndarray
        Integer label image.
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
        Integer label image.
    image : numpy.ndarray
        Image data aligned to ``labels``.
    label_ids : numpy.ndarray
        Label ids to extract sums for.

    Returns
    -------
    numpy.ndarray
        Raw integrated intensities for each provided label id.
    """
    labels_flat = labels.ravel()
    image_flat = np.nan_to_num(image.ravel(), nan=0.0)
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    sums = np.bincount(labels_flat, weights=image_flat, minlength=max_label + 1)
    return sums[label_ids]


def _safe_float(value) -> float | None:
    """Convert a metadata value to float when possible.

    Parameters
    ----------
    value : object
        Metadata value to convert.

    Returns
    -------
    float or None
        Converted value, or ``None`` when conversion fails.
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
        Napari layer providing ``metadata``.
    ndim : int
        Dimensionality of the labels or image array.

    Returns
    -------
    numpy.ndarray or None
        Per-axis pixel sizes in micrometers, ordered to match array axes.
        Returns ``None`` when metadata is missing or incomplete.

    Notes
    -----
    The SenoQuant reader stores sizes under
    ``layer.metadata["physical_pixel_sizes"]`` using ``"Z"``, ``"Y"``,
    and ``"X"`` keys (micrometers).
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
    size_x, size_y, size_z : object
        Physical sizes from metadata (may be ``None`` or non-numeric).
    ndim : int
        Dimensionality of the labels or image array.

    Returns
    -------
    numpy.ndarray or None
        Axis-ordered pixel sizes in micrometers, or ``None`` if sizes are
        incomplete or ``ndim`` is unsupported.
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
        Per-axis pixel sizes in micrometers. When provided, physical
        centroid columns are added.

    Returns
    -------
    list of dict
        Row dictionaries with ``label_id`` and centroid columns.
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
        Output rows to update in-place.
    labels : numpy.ndarray
        Label image used to compute ROI intersections.
    label_ids : numpy.ndarray
        Label ids corresponding to the output rows.
    viewer : object or None
        Napari viewer used to resolve shapes layers.
    rois : sequence of ROIConfig
        ROI configuration entries to evaluate.
    label_name : str
        Name of the labels layer, used in warning messages.
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
    """Return the raw masks array from a shapes layer.

    Parameters
    ----------
    layer : object
        Napari shapes layer instance.
    shape : tuple of int
        Target mask shape.

    Returns
    -------
    numpy.ndarray or None
        Raw masks array, or ``None`` if rendering fails.
    """
    to_masks = getattr(layer, "to_masks", None)
    if callable(to_masks):
        try:
            return np.asarray(to_masks(mask_shape=shape))
        except Exception:
            return None
    return None


def _spot_cell_ids_from_centroids(
    cell_labels: np.ndarray, centroids: np.ndarray
) -> np.ndarray:
    """Assign each spot to a cell id using its centroid position.

    Parameters
    ----------
    cell_labels : numpy.ndarray
        Cell segmentation labels array.
    centroids : numpy.ndarray
        Spot centroid coordinates in pixel units.

    Returns
    -------
    numpy.ndarray
        Cell id for each spot, with ``0`` indicating background.
    """
    if centroids.size == 0:
        return np.empty((0,), dtype=int)
    coords = np.round(centroids).astype(int)
    max_indices = np.asarray(cell_labels.shape) - 1
    coords = np.clip(coords, 0, max_indices)
    indices = tuple(coords[:, axis] for axis in range(coords.shape[1]))
    return cell_labels[indices].astype(int)


def _cell_spot_metrics(
    cell_ids: np.ndarray, spot_means: np.ndarray, max_cell: int
) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-cell spot counts and mean intensities.

    Parameters
    ----------
    cell_ids : numpy.ndarray
        Cell ids for valid spots.
    spot_means : numpy.ndarray
        Mean intensity for each valid spot.
    max_cell : int
        Maximum label id in the cell segmentation.

    Returns
    -------
    tuple of numpy.ndarray
        ``(counts, means)`` arrays indexed by cell id.
    """
    counts = np.bincount(cell_ids, minlength=max_cell + 1)
    mean_sum = np.bincount(
        cell_ids, weights=spot_means, minlength=max_cell + 1
    )
    mean_values = _safe_divide(mean_sum, counts)
    return counts, mean_values


def _append_cell_metrics(
    rows: list[dict[str, object]],
    counts: np.ndarray,
    means: np.ndarray,
    channel_label: str,
    header: list[str],
) -> None:
    """Append channel spot metrics to cell rows.

    Parameters
    ----------
    rows : list of dict
        Cell rows to update in-place.
    counts : numpy.ndarray
        Spot counts per row.
    means : numpy.ndarray
        Mean spot intensity per row.
    channel_label : str
        Display label for the channel.
    header : list of str
        Header list to extend with the new column names.
    """
    prefix = _sanitize_name(channel_label)
    count_key = f"{prefix}_spot_count"
    mean_key = f"{prefix}_spot_mean_intensity"
    for row, count, mean in zip(rows, counts, means):
        row[count_key] = int(count)
        row[mean_key] = float(mean) if np.isfinite(mean) else np.nan
    header.extend([count_key, mean_key])


def _spot_rows(
    spot_ids: np.ndarray,
    cell_ids: np.ndarray,
    centroids: np.ndarray,
    areas_px: np.ndarray,
    mean_intensity: np.ndarray,
    channel_label: str,
    pixel_sizes: np.ndarray | None,
    roi_columns: list[tuple[str, np.ndarray]],
) -> list[dict[str, object]]:
    """Build per-spot rows for export.

    Parameters
    ----------
    spot_ids : numpy.ndarray
        Spot label identifiers.
    cell_ids : numpy.ndarray
        Cell ids associated with each spot.
    centroids : numpy.ndarray
        Spot centroid coordinates in pixel units.
    areas_px : numpy.ndarray
        Spot area (2D) or volume (3D) in pixel units.
    mean_intensity : numpy.ndarray
        Mean intensity of each spot for the channel image.
    channel_label : str
        Display label for the channel to store in the row.
    pixel_sizes : numpy.ndarray or None
        Per-axis pixel sizes in micrometers. When provided, physical
        centroid coordinates and area/volume are included.
    roi_columns : list of tuple
        Precomputed ROI column names and boolean masks.

    Returns
    -------
    list of dict
        Rows ready for serialization in the spots table.
    """
    rows: list[dict[str, object]] = []
    axes = _axis_names(centroids.shape[1] if centroids.size else 0)
    size_key_px, size_key_um, size_scale = _spot_size_keys(
        centroids.shape[1] if centroids.size else 0, pixel_sizes
    )
    roi_values = _spot_roi_values(centroids, roi_columns)
    for idx, (spot_id, cell_id, centroid, area_px, mean_val) in enumerate(
        zip(spot_ids, cell_ids, centroids, areas_px, mean_intensity)
    ):
        row: dict[str, object] = {
            "spot_id": int(spot_id),
            "cell_id": int(cell_id),
            "channel": channel_label,
        }
        for axis, value in zip(axes, centroid):
            row[f"centroid_{axis}_pixels"] = float(value)
        if pixel_sizes is not None and pixel_sizes.size == len(axes):
            for axis, value, scale in zip(axes, centroid, pixel_sizes):
                row[f"centroid_{axis}_um"] = float(value * scale)
        row[size_key_px] = float(area_px)
        if size_scale is not None and size_key_um:
            row[size_key_um] = float(area_px * size_scale)
        row["spot_mean_intensity"] = (
            float(mean_val) if np.isfinite(mean_val) else np.nan
        )
        for column, values in roi_values:
            row[column] = int(values[idx])
        rows.append(row)
    return rows


def _spot_size_keys(
    ndim: int, pixel_sizes: np.ndarray | None
) -> tuple[str, str | None, float | None]:
    """Return size column names and physical scale for spot sizes.

    Parameters
    ----------
    ndim : int
        Number of spatial dimensions.
    pixel_sizes : numpy.ndarray or None
        Per-axis pixel sizes in micrometers.

    Returns
    -------
    tuple
        ``(pixel_key, physical_key, scale)`` where ``scale`` is the
        multiplicative factor to convert pixel area/volume to physical
        units, or ``None`` if physical sizes are unavailable.
    """
    if ndim == 3:
        size_key_px = "spot_volume_pixels"
        size_key_um = "spot_volume_um3"
    else:
        size_key_px = "spot_area_pixels"
        size_key_um = "spot_area_um2"
    if pixel_sizes is None:
        return size_key_px, None, None
    scale = float(np.prod(pixel_sizes))
    return size_key_px, size_key_um, scale


def _spot_roi_columns(
    viewer: object | None,
    rois: Sequence["ROIConfig"],
    label_name: str,
    shape: tuple[int, ...],
) -> list[tuple[str, np.ndarray]]:
    """Prepare ROI mask columns for spots export.

    Parameters
    ----------
    viewer : object or None
        Napari viewer instance used to resolve shapes layers.
    rois : sequence of ROIConfig
        ROI configuration entries to evaluate.
    label_name : str
        Name of the labels layer, used in warning messages.
    shape : tuple of int
        Target mask shape matching the labels array.

    Returns
    -------
    list of tuple
        List of ``(column_name, mask)`` entries for ROI membership.
    """
    if viewer is None or not rois:
        return []
    columns: list[tuple[str, np.ndarray]] = []
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
        mask = _shapes_layer_mask(shapes_layer, shape)
        if mask is None:
            warnings.warn(
                f"ROI layer '{layer_name}' could not be rasterized.",
                RuntimeWarning,
            )
            continue
        roi_name = getattr(roi, "name", "") or f"roi_{index}"
        roi_type = getattr(roi, "roi_type", "Include") or "Include"
        if roi_type.lower() == "exclude":
            prefix = "excluded_from_roi"
        else:
            prefix = "included_in_roi"
        column = f"{prefix}_{_sanitize_name(roi_name)}"
        columns.append((column, mask))
    return columns


def _spot_roi_values(
    centroids: np.ndarray, roi_columns: list[tuple[str, np.ndarray]]
) -> list[tuple[str, np.ndarray]]:
    """Return ROI membership values for each spot centroid.

    Parameters
    ----------
    centroids : numpy.ndarray
        Spot centroid coordinates in pixel units.
    roi_columns : list of tuple
        ROI columns from :func:`_spot_roi_columns`.

    Returns
    -------
    list of tuple
        List of ``(column_name, values)`` pairs aligned to the spot order.
    """
    if not roi_columns or centroids.size == 0:
        return []
    coords = np.round(centroids).astype(int)
    roi_values: list[tuple[str, np.ndarray]] = []
    for column, mask in roi_columns:
        max_indices = np.asarray(mask.shape) - 1
        clipped = np.clip(coords, 0, max_indices)
        indices = tuple(
            clipped[:, axis] for axis in range(clipped.shape[1])
        )
        values = mask[indices].astype(int)
        roi_values.append((column, values))
    return roi_values


def _spot_header(
    ndim: int,
    pixel_sizes: np.ndarray | None,
    roi_columns: list[tuple[str, np.ndarray]],
) -> list[str]:
    """Build the header for the spots table.

    Parameters
    ----------
    ndim : int
        Number of spatial dimensions.
    pixel_sizes : numpy.ndarray or None
        Per-axis pixel sizes in micrometers.
    roi_columns : list of tuple
        ROI columns to append to the header.

    Returns
    -------
    list of str
        Column names for the spots export table.
    """
    axes = _axis_names(ndim)
    size_key_px, size_key_um, _scale = _spot_size_keys(ndim, pixel_sizes)
    header = ["spot_id", "cell_id", "channel"]
    header.extend([f"centroid_{axis}_pixels" for axis in axes])
    if pixel_sizes is not None and pixel_sizes.size == len(axes):
        header.extend([f"centroid_{axis}_um" for axis in axes])
    header.append(size_key_px)
    if size_key_um:
        header.append(size_key_um)
    header.append("spot_mean_intensity")
    if roi_columns:
        header.extend([column for column, _mask in roi_columns])
    return header


def _channel_label(channel) -> str:
    """Return a display label for a channel.

    Parameters
    ----------
    channel : object
        Channel configuration object.

    Returns
    -------
    str
        Human-readable label for the channel.
    """
    label = channel.name.strip() if channel.name else ""
    return label or channel.channel


def _sanitize_name(value: str) -> str:
    """Normalize names for filenames and column prefixes.

    Parameters
    ----------
    value : str
        Raw name to sanitize.

    Returns
    -------
    str
        Lowercase name with spaces normalized and unsafe characters removed.
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
        Division results with zeros where denominator is zero.
    """
    result = np.zeros_like(numerator, dtype=float)
    np.divide(numerator, denominator, out=result, where=denominator != 0)
    return result


def _write_table(
    path: Path, header: list[str], rows: list[dict[str, object]], fmt: str
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

    Raises
    ------
    RuntimeError
        If ``fmt`` is ``"xlsx"`` and ``openpyxl`` is unavailable.
    ValueError
        If ``fmt`` is not a supported format.
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
