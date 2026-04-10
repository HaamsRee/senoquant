"""Summary plotting for instance-based benchmark outputs."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .data import configure_matplotlib_cache
from .matching import PLOT_METRIC_FIELDS, PLOT_METRIC_LABELS
from .results import read_dataset_summary_rows


def write_summary_plot(
    *,
    csv_dir: Path,
    plot_path: Path,
    title: str,
) -> None:
    """Write a threshold-aware summary plot from benchmark CSV files."""
    configure_matplotlib_cache()
    import matplotlib.pyplot as plt

    csv_paths = [
        path
        for path in sorted(csv_dir.glob("*.csv"))
        if path.is_file() and not path.name.startswith(".")
    ]
    summaries = read_dataset_summary_rows(csv_paths)
    if not summaries:
        raise ValueError(f"No benchmark CSV files found in {csv_dir}")

    thresholds = sorted(
        {
            float(row["iou_threshold"])
            for rows in summaries.values()
            for row in rows
        }
    )
    x_values = np.asarray(thresholds, dtype=float)
    figure, axes = plt.subplots(2, 2, figsize=(12, 9), sharex=True, sharey=True)

    for axis, metric_name in zip(axes.flat, PLOT_METRIC_FIELDS, strict=True):
        for model_name, rows in summaries.items():
            metric_by_threshold = {
                float(row["iou_threshold"]): float(row[metric_name]) for row in rows
            }
            y_values = [metric_by_threshold.get(threshold, np.nan) for threshold in thresholds]
            axis.plot(x_values, y_values, marker="o", linewidth=2, label=model_name)

        axis.set_title(PLOT_METRIC_LABELS[metric_name])
        axis.set_ylim(0.0, 1.04)
        axis.set_xticks(x_values)
        axis.grid(axis="both", alpha=0.3)
        axis.set_axisbelow(True)

    figure.suptitle(title)
    figure.text(0.5, 0.04, "IoU Threshold", ha="center")
    figure.text(0.04, 0.5, "Score", va="center", rotation="vertical")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="upper center", ncol=min(len(labels), 4))

    plot_path.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout(rect=(0.05, 0.06, 1.0, 0.92))
    figure.savefig(plot_path, dpi=200)
    plt.close(figure)
