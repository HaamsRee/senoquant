"""CSV row helpers for instance-based benchmark outputs."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .matching import CSV_VALUE_FIELDS, InstanceMetrics

CSV_FIELDNAMES: tuple[str, ...] = (
    "row_type",
    "case_id",
    "model",
    "criterion",
    "iou_threshold",
    *CSV_VALUE_FIELDS,
)


def make_case_row(
    *,
    case_id: str,
    model_name: str,
    metrics: InstanceMetrics,
) -> dict[str, object]:
    """Serialize one case-level metric object into a CSV row."""
    return _make_row(
        row_type="case",
        case_id=case_id,
        model_name=model_name,
        metrics=metrics,
    )


def make_dataset_summary_row(
    *,
    model_name: str,
    metrics: InstanceMetrics,
) -> dict[str, object]:
    """Serialize one dataset-level metric object into a CSV row."""
    return _make_row(
        row_type="dataset_summary",
        case_id="DATASET",
        model_name=model_name,
        metrics=metrics,
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write benchmark rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        writer.writerows(rows)


def read_dataset_summary_rows(
    csv_paths: Iterable[Path],
) -> dict[str, list[dict[str, float | str]]]:
    """Read dataset-summary rows from one or more benchmark CSV files."""
    summaries: dict[str, list[dict[str, float | str]]] = defaultdict(list)
    for csv_path in sorted(csv_paths):
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("row_type") != "dataset_summary":
                    continue
                if any(metric_name not in row for metric_name in CSV_VALUE_FIELDS):
                    continue
                model_name = row.get("model", "").strip() or csv_path.stem
                summaries[model_name].append(
                    {
                        "criterion": row["criterion"],
                        "iou_threshold": float(row["iou_threshold"]),
                        **{
                            metric_name: float(row[metric_name])
                            for metric_name in CSV_VALUE_FIELDS
                        },
                    }
                )

    for rows in summaries.values():
        rows.sort(key=lambda row: float(row["iou_threshold"]))
    return dict(summaries)


def _make_row(
    *,
    row_type: str,
    case_id: str,
    model_name: str,
    metrics: InstanceMetrics,
) -> dict[str, object]:
    """Convert an :class:`InstanceMetrics` object into a CSV row."""
    row: dict[str, object] = {
        "row_type": row_type,
        "case_id": case_id,
        "model": model_name,
        "criterion": metrics.criterion,
        "iou_threshold": metrics.iou_threshold,
    }
    for field_name in CSV_VALUE_FIELDS:
        row[field_name] = getattr(metrics, field_name)
    return row
