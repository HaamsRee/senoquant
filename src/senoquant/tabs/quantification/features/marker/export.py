"""Marker feature export logic."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import numpy as np
from skimage.measure import regionprops_table

from .config import MarkerFeatureData
from ..base import FeatureConfig


def export_marker(
    feature: FeatureConfig,
    temp_dir: Path,
    viewer=None,
    export_format: str = "csv",
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

    Returns
    -------
    iterable of Path
        Paths to files produced by the export routine.
    """
    data = feature.data
    if not isinstance(data, MarkerFeatureData) or viewer is None:
        return []

    export_format = (export_format or "csv").lower()
    outputs: list[Path] = []
    channels = [channel for channel in data.channels if channel.channel]
    if not data.segmentations or not channels:
        return []

    for index, segmentation in enumerate(data.segmentations, start=1):
        label_name = segmentation.label.strip()
        if not label_name:
            continue
        labels_layer = _find_layer(viewer, label_name, "Labels")
        if labels_layer is None:
            continue
        labels = np.asarray(labels_layer.data)
        if labels.size == 0:
            continue

        label_ids, centroids = _compute_centroids(labels)
        if label_ids.size == 0:
            continue
        area_px = _pixel_counts(labels, label_ids)

        rows = _initialize_rows(label_ids, centroids)
        header = list(rows[0].keys()) if rows else []

        for channel in channels:
            channel_layer = _find_layer(viewer, channel.channel, "Image")
            if channel_layer is None:
                continue
            image = np.asarray(channel_layer.data)
            if image.shape != labels.shape:
                continue
            raw_sum = _intensity_sum(labels, image, label_ids)
            mean_intensity = _safe_divide(raw_sum, area_px)
            pixel_volume = _pixel_volume(channel_layer, labels.ndim)
            integrated = mean_intensity * (area_px * pixel_volume)
            prefix = _channel_prefix(channel)
            for row, mean_val, raw_val, int_val in zip(
                rows, mean_intensity, raw_sum, integrated
            ):
                row[f"{prefix}_mean_intensity"] = float(mean_val)
                row[f"{prefix}_integrated_intensity"] = float(int_val)
                row[f"{prefix}_raw_integrated_intensity"] = float(raw_val)
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

        if not rows:
            continue
        file_stem = _sanitize_name(label_name or f"segmentation_{index}")
        output_path = temp_dir / f"{file_stem}.{export_format}"
        _write_table(output_path, header, rows, export_format)
        outputs.append(output_path)

    return outputs


def _find_layer(viewer, name: str, layer_type: str):
    """Return a layer by name and class name."""
    for layer in viewer.layers:
        if layer.__class__.__name__ == layer_type and layer.name == name:
            return layer
    return None


def _compute_centroids(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute centroid coordinates for each non-zero label."""
    props = regionprops_table(labels, properties=("label", "centroid"))
    label_ids = np.asarray(props.get("label", []), dtype=int)
    centroid_cols = [key for key in props if key.startswith("centroid-")]
    if not centroid_cols:
        return label_ids, np.empty((0, labels.ndim), dtype=float)
    centroids = np.column_stack([props[key] for key in centroid_cols]).astype(float)
    return label_ids, centroids


def _pixel_counts(labels: np.ndarray, label_ids: np.ndarray) -> np.ndarray:
    """Return pixel counts for each label id."""
    labels_flat = labels.ravel()
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    counts = np.bincount(labels_flat, minlength=max_label + 1)
    return counts[label_ids]


def _intensity_sum(
    labels: np.ndarray, image: np.ndarray, label_ids: np.ndarray
) -> np.ndarray:
    """Return raw intensity sums for each label id."""
    labels_flat = labels.ravel()
    image_flat = np.nan_to_num(image.ravel(), nan=0.0)
    max_label = int(labels_flat.max()) if labels_flat.size else 0
    sums = np.bincount(labels_flat, weights=image_flat, minlength=max_label + 1)
    return sums[label_ids]


def _pixel_volume(layer, ndim: int) -> float:
    """Compute the per-pixel physical volume based on layer scale."""
    scale = getattr(layer, "scale", None)
    if scale is None:
        return 1.0
    scale_vals = np.asarray(scale, dtype=float)
    if scale_vals.size == 0:
        return 1.0
    if scale_vals.size != ndim:
        scale_vals = scale_vals[-ndim:]
    return float(np.prod(scale_vals))


def _axis_names(ndim: int) -> list[str]:
    """Return axis suffixes for centroid columns."""
    if ndim == 2:
        return ["y", "x"]
    if ndim == 3:
        return ["z", "y", "x"]
    return [f"axis_{idx}" for idx in range(ndim)]


def _initialize_rows(
    label_ids: np.ndarray, centroids: np.ndarray
) -> list[dict[str, float]]:
    """Initialize output rows with label ids and centroid coordinates."""
    axes = _axis_names(centroids.shape[1] if centroids.size else 0)
    rows: list[dict[str, float]] = []
    for label_id, centroid in zip(label_ids, centroids):
        row: dict[str, float] = {"label_id": int(label_id)}
        for axis, value in zip(axes, centroid):
            row[f"centroid_{axis}"] = float(value)
        rows.append(row)
    return rows


def _channel_prefix(channel) -> str:
    """Return a sanitized column prefix for a channel."""
    name = channel.name.strip() if channel.name else ""
    if not name:
        name = channel.channel
    return _sanitize_name(name)


def _sanitize_name(value: str) -> str:
    """Normalize names for filenames and column prefixes."""
    cleaned = "".join(
        char if char.isalnum() or char in "-_ " else "_" for char in value
    )
    return cleaned.strip().replace(" ", "_").lower()


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Compute numerator/denominator with zero-safe handling."""
    result = np.zeros_like(numerator, dtype=float)
    np.divide(
        numerator,
        denominator,
        out=result,
        where=denominator != 0,
    )
    return result


def _write_table(
    path: Path, header: list[str], rows: list[dict[str, float]], fmt: str
) -> None:
    """Write rows to disk as CSV or XLSX."""
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
