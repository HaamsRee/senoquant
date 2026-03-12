"""Post-processing helpers for marker exports."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from senoquant.utils import layer_data_asarray
from senoquant.utils.naming import build_name_token_map
from .config import MarkerFeatureData
from .export import _find_layer, _write_table

if TYPE_CHECKING:
    from ..base import FeatureConfig


@dataclass(frozen=True)
class MarkerSegmentationTable:
    """Resolved marker table metadata for merged export."""

    label_name: str
    token: str
    segmentation_type: str
    prefix: str
    header: list[str]
    rows_by_label_id: dict[int, dict[str, object]]


def postprocess_marker_merged_wide(
    feature: "FeatureConfig",
    temp_dir: Path,
    outputs: list[Path],
    *,
    viewer=None,
    export_format: str = "csv",
) -> list[Path]:
    """Append a merged wide marker table when strict 1:1 matching exists."""
    data = feature.data
    if not isinstance(data, MarkerFeatureData):
        return outputs
    if viewer is None or not data.merge_tables_across_segmentations:
        return outputs

    valid_segmentation_names = _valid_segmentation_names(data, viewer)
    if len(valid_segmentation_names) < 2:
        return outputs
    if len(valid_segmentation_names) != len(set(valid_segmentation_names)):
        _log_merge_skip(
            feature,
            "duplicate segmentation layer names prevent strict merged export",
        )
        return outputs

    segmentation_tokens = build_name_token_map(
        valid_segmentation_names,
        fallback="segmentation",
    )
    lower_format = (export_format or "csv").lower()
    table_paths_by_token = _marker_table_paths_by_token(
        outputs,
        lower_format,
        set(segmentation_tokens.values()),
    )
    if len(table_paths_by_token) < 2:
        return outputs

    tables: list[MarkerSegmentationTable] = []
    for label_name in valid_segmentation_names:
        token = segmentation_tokens[label_name]
        path = table_paths_by_token.get(token)
        if path is None:
            _log_merge_skip(
                feature,
                f"missing exported table for segmentation '{label_name}'",
            )
            return outputs
        header, rows = _read_table(path)
        table, reason = _build_segmentation_table(
            label_name=label_name,
            token=token,
            header=header,
            rows=rows,
        )
        if reason is not None:
            _log_merge_skip(feature, reason)
            return outputs
        tables.append(table)

    tables = _assign_short_prefixes(tables)

    reason = _validate_shared_label_ids(tables)
    if reason is not None:
        _log_merge_skip(feature, reason)
        return outputs

    reason = _validate_strict_correspondence(tables)
    if reason is not None:
        _log_merge_skip(feature, reason)
        return outputs

    merged_header, merged_rows = _build_merged_table(tables)
    merged_path = temp_dir / f"merged_wide.{lower_format}"
    _write_table(merged_path, merged_header, merged_rows, lower_format)
    return [*outputs, merged_path]


def _valid_segmentation_names(
    data: MarkerFeatureData,
    viewer: object,
) -> list[str]:
    """Return valid marker segmentation layer names in export order."""
    valid_names: list[str] = []
    for segmentation in data.segmentations:
        label_name = segmentation.label.strip()
        if not label_name:
            continue
        labels_layer = _find_layer(viewer, label_name, "Labels")
        if labels_layer is None:
            continue
        labels = layer_data_asarray(labels_layer)
        if labels.size == 0:
            continue
        if not np.any(np.asarray(labels) > 0):
            continue
        valid_names.append(label_name)
    return valid_names


def _marker_table_paths_by_token(
    outputs: list[Path],
    export_format: str,
    segmentation_tokens: set[str],
) -> dict[str, Path]:
    """Return marker table paths keyed by segmentation token."""
    expected_suffix = f".{export_format}"
    table_paths: dict[str, Path] = {}
    for path in outputs:
        if path.suffix.lower() != expected_suffix:
            continue
        if path.stem == "merged_wide":
            continue
        if path.stem not in segmentation_tokens:
            continue
        table_paths[path.stem] = path
    return table_paths


def _build_segmentation_table(
    *,
    label_name: str,
    token: str,
    header: list[str],
    rows: list[dict[str, object]],
) -> tuple[MarkerSegmentationTable | None, str | None]:
    """Build a validated segmentation table model from exported rows."""
    missing = [column for column in ("label_id", "overlaps_with") if column not in header]
    if missing:
        return None, (
            f"table '{token}' is missing required column(s): {', '.join(missing)}"
        )
    segmentation_type, reason = _resolve_segmentation_type(
        token=token,
        header=header,
        rows=rows,
    )
    if reason is not None:
        return None, reason

    rows_by_label_id: dict[int, dict[str, object]] = {}
    for row in rows:
        label_id, error = _coerce_label_id(row.get("label_id"))
        if error is not None:
            return None, f"table '{token}' has invalid label_id: {error}"
        assert label_id is not None
        if label_id in rows_by_label_id:
            return None, f"table '{token}' has duplicate row for label_id={label_id}"
        rows_by_label_id[label_id] = row
    if not rows_by_label_id:
        return None, f"table '{token}' does not contain any exported rows"

    return (
        MarkerSegmentationTable(
            label_name=label_name,
            token=token,
            segmentation_type=segmentation_type,
            prefix="",
            header=header,
            rows_by_label_id=rows_by_label_id,
        ),
        None,
    )


def _resolve_segmentation_type(
    *,
    token: str,
    header: list[str],
    rows: list[dict[str, object]],
) -> tuple[str, str | None]:
    """Return a consistent segmentation type token for one table."""
    if "segmentation_type" not in header:
        return "segmentation", None

    values = {
        str(row.get("segmentation_type", "")).strip().lower()
        for row in rows
        if str(row.get("segmentation_type", "")).strip()
    }
    if not values:
        return "segmentation", None
    if len(values) != 1:
        return (
            "",
            f"table '{token}' has inconsistent segmentation_type values",
        )
    return next(iter(values)), None


def _assign_short_prefixes(
    tables: list[MarkerSegmentationTable],
) -> list[MarkerSegmentationTable]:
    """Return tables with short, deterministic type-based prefixes."""
    counts: dict[str, int] = {}
    resolved: list[MarkerSegmentationTable] = []
    for table in tables:
        base = _short_prefix_base(table.segmentation_type)
        counts[base] = counts.get(base, 0) + 1
        resolved.append(
            replace(
                table,
                prefix=f"{base}_{counts[base]}",
            )
        )
    return resolved


def _short_prefix_base(segmentation_type: str) -> str:
    """Return a concise merged-table prefix base for one segmentation type."""
    normalized = segmentation_type.strip().lower()
    if normalized == "nuclear" or normalized.startswith("nuc"):
        return "nuclear"
    if normalized == "cytoplasmic" or normalized.startswith("cyto"):
        return "cyto"
    return "seg"


def _validate_shared_label_ids(
    tables: list[MarkerSegmentationTable],
) -> str | None:
    """Require identical label_id sets across all segmentation tables."""
    if not tables:
        return None
    expected_ids = set(tables[0].rows_by_label_id)
    for table in tables[1:]:
        actual_ids = set(table.rows_by_label_id)
        if actual_ids != expected_ids:
            return (
                f"table '{table.token}' does not share the same label_id set as "
                f"table '{tables[0].token}'"
            )
    return None


def _validate_strict_correspondence(
    tables: list[MarkerSegmentationTable],
) -> str | None:
    """Require exact same-id overlap references across all segmentations."""
    tokens = [table.token for table in tables]
    for table in tables:
        other_tokens = [token for token in tokens if token != table.token]
        for label_id, row in table.rows_by_label_id.items():
            actual_refs = _split_overlap_refs(row.get("overlaps_with"))
            if len(actual_refs) != len(set(actual_refs)):
                return (
                    f"table '{table.token}' label_id={label_id} has duplicate "
                    "overlap references"
                )
            expected_refs = {
                f"{other_token}_{label_id}" for other_token in other_tokens
            }
            actual_ref_set = set(actual_refs)
            if actual_ref_set != expected_refs:
                missing_refs = sorted(expected_refs - actual_ref_set)
                extra_refs = sorted(actual_ref_set - expected_refs)
                if missing_refs:
                    return (
                        f"table '{table.token}' label_id={label_id} is missing "
                        f"expected overlap '{missing_refs[0]}'"
                    )
                if extra_refs:
                    return (
                        f"table '{table.token}' label_id={label_id} has unexpected "
                        f"overlap '{extra_refs[0]}'"
                    )
                return (
                    f"table '{table.token}' label_id={label_id} failed strict "
                    "overlap validation"
                )
    return None


def _build_merged_table(
    tables: list[MarkerSegmentationTable],
) -> tuple[list[str], list[dict[str, object]]]:
    """Return merged header and rows for strict 1:1 marker tables."""
    merged_header = ["merge_label_id"]
    for table in tables:
        merged_header.append(f"{table.prefix}_segmentation_name")
        merged_header.append(f"{table.prefix}_segmentation_token_name")
        merged_header.extend(
            f"{table.prefix}_{column}"
            for column in table.header
            if column != "segmentation_type"
        )

    merged_rows: list[dict[str, object]] = []
    shared_ids = sorted(tables[0].rows_by_label_id)
    for label_id in shared_ids:
        merged_row: dict[str, object] = {"merge_label_id": label_id}
        for table in tables:
            merged_row[f"{table.prefix}_segmentation_name"] = table.label_name
            merged_row[f"{table.prefix}_segmentation_token_name"] = table.token
            source_row = table.rows_by_label_id[label_id]
            for column in table.header:
                if column == "segmentation_type":
                    continue
                merged_row[f"{table.prefix}_{column}"] = source_row.get(column)
        merged_rows.append(merged_row)
    return merged_header, merged_rows


def _read_table(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    """Read a marker export table from CSV or XLSX."""
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            header = list(reader.fieldnames or [])
            rows = list(reader)
        return header, rows

    if path.suffix.lower() == ".xlsx":
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openpyxl is required for xlsx export") from exc
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            values = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
        if not values:
            return [], []
        header = [str(value) if value is not None else "" for value in values[0]]
        rows: list[dict[str, object]] = []
        for row_values in values[1:]:
            if row_values is None:
                continue
            if all(value is None for value in row_values):
                continue
            row = {
                column: value
                for column, value in zip(header, row_values, strict=False)
            }
            rows.append(row)
        return header, rows

    raise ValueError(f"Unsupported marker table format: {path.suffix}")


def _coerce_label_id(value: object) -> tuple[int | None, str | None]:
    """Return an integer label id or a concrete parse error."""
    if value is None:
        return None, "missing value"
    text = str(value).strip()
    if not text:
        return None, "blank value"
    try:
        numeric = float(text)
    except ValueError:
        return None, text
    if not numeric.is_integer():
        return None, text
    return int(numeric), None


def _split_overlap_refs(value: object) -> list[str]:
    """Return cleaned overlap reference tokens from a cell value."""
    if value is None:
        return []
    return [
        part.strip()
        for part in str(value).split(";")
        if part is not None and part.strip()
    ]


def _log_merge_skip(feature: "FeatureConfig", reason: str) -> None:
    """Print a non-blocking merged-table skip message."""
    feature_name = feature.name.strip() or feature.type_name or "Markers"
    print(
        f"Marker merged table skipped for feature '{feature_name}': {reason}",
    )
    try:
        sys.stdout.flush()
    except Exception:  # pragma: no cover - best effort flush
        pass
