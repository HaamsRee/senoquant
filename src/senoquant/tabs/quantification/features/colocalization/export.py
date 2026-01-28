"""Colocalization feature export logic."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Iterable

import numpy as np

from senoquant.utils import layer_data_asarray
from ..base import FeatureConfig
from ..spots.config import SpotsFeatureData
from ..spots.export import (
    _add_roi_columns,
    _channel_label,
    _compute_centroids,
    _find_layer,
    _initialize_rows,
    _intensity_sum,
    _pixel_counts,
    _pixel_sizes,
    _safe_divide,
    _sanitize_name,
    _spot_cell_ids_from_centroids,
    _spot_header,
    _spot_roi_columns,
    _spot_rows,
    _write_table,
)


def export_colocalization(
    feature: FeatureConfig,
    spots_feature: FeatureConfig,
    temp_dir: Path,
    viewer=None,
    export_format: str = "csv",
) -> Iterable[Path]:
    """Export colocalization outputs into a temporary directory.

    Parameters
    ----------
    feature : FeatureConfig
        Colocalization feature configuration (unused beyond metadata).
    spots_feature : FeatureConfig
        Spots feature configuration that provides channel/segmentation data.
    temp_dir : Path
        Temporary directory where outputs should be written.
    viewer : object, optional
        Napari viewer instance used to resolve layers by name and read data.
        When ``None``, export is skipped.
    export_format : str, optional
        File format for exports (``"csv"`` or ``"xlsx"``).

    Returns
    -------
    iterable of Path
        Paths to files produced by the export routine.
    """
    data = spots_feature.data
    if not isinstance(data, SpotsFeatureData) or viewer is None:
        return []

    export_format = (export_format or "csv").lower()
    outputs: list[Path] = []
    channels = [
        channel
        for channel in data.channels
        if channel.channel and channel.spots_segmentation
    ]
    if not data.segmentations or len(channels) < 2:
        return []

    first_channel_layer = None
    for channel in channels:
        first_channel_layer = _find_layer(viewer, channel.channel, "Image")
        if first_channel_layer is not None:
            break

    for index, segmentation in enumerate(data.segmentations, start=0):
        label_name = segmentation.label.strip()
        if not label_name:
            continue
        labels_layer = _find_layer(viewer, label_name, "Labels")
        if labels_layer is None:
            continue
        cell_labels = layer_data_asarray(labels_layer)
        if cell_labels.size == 0:
            continue

        cell_ids, cell_centroids = _compute_centroids(cell_labels)
        if cell_ids.size == 0:
            continue

        cell_pixel_sizes = _pixel_sizes(labels_layer, cell_labels.ndim)
        if cell_pixel_sizes is None and first_channel_layer is not None:
            cell_pixel_sizes = _pixel_sizes(
                first_channel_layer, cell_labels.ndim
            )

        cell_rows = _initialize_rows(
            cell_ids, cell_centroids, cell_pixel_sizes
        )
        _add_roi_columns(
            cell_rows,
            cell_labels,
            cell_ids,
            viewer,
            data.rois,
            label_name,
        )
        cell_header = list(cell_rows[0].keys()) if cell_rows else []

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

        channel_data: list[dict[str, object]] = []
        for channel in channels:
            channel_label = _channel_label(channel)
            channel_layer = _find_layer(viewer, channel.channel, "Image")
            spots_layer = _find_layer(
                viewer, channel.spots_segmentation, "Labels"
            )
            if spots_layer is None:
                warnings.warn(
                    "Colocalization export: spots segmentation layer "
                    f"'{channel.spots_segmentation}' not found.",
                    RuntimeWarning,
                )
                continue
            spots_labels = layer_data_asarray(spots_layer)
            if spots_labels.shape != cell_labels.shape:
                warnings.warn(
                    "Colocalization export: segmentation shape mismatch "
                    f"for '{label_name}' vs "
                    f"'{channel.spots_segmentation}'. Skipping.",
                    RuntimeWarning,
                )
                continue
            channel_data.append(
                {
                    "label": channel_label,
                    "spots_labels": spots_labels,
                    "channel_layer": channel_layer,
                }
            )

        adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
        for idx_a, data_a in enumerate(channel_data):
            labels_a = data_a["spots_labels"]
            for idx_b in range(idx_a + 1, len(channel_data)):
                labels_b = channel_data[idx_b]["spots_labels"]
                mask = (labels_a > 0) & (labels_b > 0)
                if not np.any(mask):
                    continue
                pairs = np.column_stack(
                    (labels_a[mask], labels_b[mask])
                )
                unique_pairs = np.unique(pairs, axis=0)
                for spot_a, spot_b in unique_pairs:
                    key_a = (idx_a, int(spot_a))
                    key_b = (idx_b, int(spot_b))
                    adjacency.setdefault(key_a, set()).add(key_b)
                    adjacency.setdefault(key_b, set()).add(key_a)

        spot_lookup: dict[
            tuple[int, int], dict[str, object]
        ] = {}
        channel_labels = [entry["label"] for entry in channel_data]

        for idx, entry in enumerate(channel_data):
            spots_labels = entry["spots_labels"]
            channel_layer = entry["channel_layer"]
            channel_label = entry["label"]

            spot_ids, spot_centroids = _compute_centroids(spots_labels)
            if spot_ids.size == 0:
                continue

            spot_area_px = _pixel_counts(spots_labels, spot_ids)
            spot_mean_intensity = None
            if channel_layer is not None:
                image = layer_data_asarray(channel_layer)
                if image.shape == spots_labels.shape:
                    raw_sum = _intensity_sum(
                        spots_labels, image, spot_ids
                    )
                    spot_mean_intensity = _safe_divide(
                        raw_sum, spot_area_px
                    )
            if spot_mean_intensity is None:
                spot_mean_intensity = np.full(
                    spot_area_px.shape, np.nan, dtype=float
                )

            cell_ids_for_spots = _spot_cell_ids_from_centroids(
                cell_labels, spot_centroids
            )
            valid_mask = cell_ids_for_spots > 0
            valid_spot_ids = spot_ids[valid_mask]
            valid_cell_ids = cell_ids_for_spots[valid_mask]
            valid_centroids = spot_centroids[valid_mask]
            valid_areas = spot_area_px[valid_mask]
            valid_means = spot_mean_intensity[valid_mask]

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
                    spot_header = list(spot_rows_for_channel[0].keys())
                for row, spot_id, cell_id in zip(
                    spot_rows_for_channel, valid_spot_ids, valid_cell_ids
                ):
                    key = (idx, int(spot_id))
                    spot_lookup[key] = {
                        "row": row,
                        "cell_id": int(cell_id),
                    }
                spot_rows.extend(spot_rows_for_channel)

        for key, info in spot_lookup.items():
            others = adjacency.get(key, set())
            names: list[str] = []
            for other in others:
                if other not in spot_lookup:
                    continue
                other_label = channel_labels[other[0]]
                names.append(f"{other_label}:{other[1]}")
            if names:
                names = sorted(set(names))
                info["row"]["colocalizes_with"] = ";".join(names)
            else:
                info["row"]["colocalizes_with"] = ""

        colocalization_key = "colocalization_event_count"
        event_counts = np.zeros(int(cell_labels.max()) + 1, dtype=int)
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
        cell_header.append(colocalization_key)

        if cell_rows:
            file_stem = _sanitize_name(
                label_name or f"segmentation_{index}"
            )
            cell_path = temp_dir / f"{file_stem}_cells.{export_format}"
            _write_table(cell_path, cell_header, cell_rows, export_format)
            outputs.append(cell_path)

        if not spot_header:
            spot_header = _spot_header(
                cell_labels.ndim, spot_table_pixel_sizes, spot_roi_columns
            )
        if "colocalizes_with" not in spot_header:
            spot_header.append("colocalizes_with")
        for row in spot_rows:
            row.setdefault("colocalizes_with", "")
        file_stem = _sanitize_name(label_name or f"segmentation_{index}")
        spot_path = temp_dir / f"{file_stem}_spots.{export_format}"
        _write_table(spot_path, spot_header, spot_rows, export_format)
        outputs.append(spot_path)

    return outputs
