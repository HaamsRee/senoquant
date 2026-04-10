"""Benchmark 2D nuclear segmentation models with instance-level metrics.

This command-line entrypoint keeps the public workflow in one place while the
benchmark implementation lives in the local ``benchmarking`` package.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmarking import (
    DEFAULT_IOU_THRESHOLDS,
    load_settings,
    run_benchmark,
    write_csv,
    write_summary_plot,
)

__all__ = [
    "DEFAULT_IOU_THRESHOLDS",
    "load_settings",
    "main",
    "run_benchmark",
    "write_csv",
    "write_summary_plot",
]


def main() -> int:
    """Run the command-line interface."""
    root = Path(__file__).resolve().parent
    default_thresholds = " ".join(f"{value:g}" for value in DEFAULT_IOU_THRESHOLDS)

    parser = argparse.ArgumentParser(
        description=(
            "Benchmark 2D nuclear segmentation masks with instance metrics."
        )
    )
    parser.add_argument("--model", required=True, help="Segmentation model name.")
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Optional root folder for external segmentation models.",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=root / "images",
        help="Folder containing input images.",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=root / "ground_truth",
        help="Folder containing ground-truth masks.",
    )
    parser.add_argument(
        "--settings-json",
        type=Path,
        default=None,
        help="Optional JSON file with model settings.",
    )
    parser.add_argument(
        "--iou-thresholds",
        type=float,
        nargs="+",
        default=list(DEFAULT_IOU_THRESHOLDS),
        help=(
            "One or more IoU thresholds used for instance matching. "
            f"Default: {default_thresholds}"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path.",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=None,
        help="Optional PNG output path for the threshold summary plot.",
    )
    parser.add_argument(
        "--plot-title",
        default=None,
        help="Optional title for the summary plot.",
    )
    args = parser.parse_args()

    settings = load_settings(args.settings_json)
    output_path = args.output or (root / "results" / f"{args.model}.csv")
    plot_path = args.plot or (output_path.parent / "benchmark_summary.png")
    plot_title = args.plot_title or args.images.resolve().name
    rows = run_benchmark(
        model_name=args.model,
        images_dir=args.images.resolve(),
        ground_truth_dir=args.ground_truth.resolve(),
        settings=settings,
        models_root=args.models_root.resolve() if args.models_root else None,
        iou_thresholds=args.iou_thresholds,
    )
    write_csv(output_path, rows)
    write_summary_plot(
        csv_dir=output_path.parent,
        plot_path=plot_path,
        title=plot_title,
    )
    print(f"Wrote {output_path}")
    print(f"Wrote {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
