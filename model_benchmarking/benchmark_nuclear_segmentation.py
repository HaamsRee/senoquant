"""Benchmark 2D single-channel nuclear segmentation models.

This script provides a small, file-based benchmarking loop for nuclear
segmentation models that follow the SenoQuant segmentation API. It is limited
to single-channel 2D inputs and compares each predicted mask against a matching
ground-truth mask using binary foreground metrics.

The benchmark intentionally avoids the full napari widget stack. Instead, it
creates a minimal image-layer wrapper, loads segmentation models through the
existing backend, writes one CSV file containing per-image scores plus a mean
row, and renders a grouped bar chart summary from all CSVs in the results
folder.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import sys
import tempfile
import types
from collections.abc import Iterable
from pathlib import Path

import numpy as np

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover - optional dependency
    tqdm = None


class ImageLayer:
    """Minimal napari-like image layer.

    Parameters
    ----------
    data : array-like
        Image data that will be exposed through the ``data`` attribute.
    name : str, optional
        Layer name passed to models that may inspect the layer metadata.

    Attributes
    ----------
    data : array-like
        Stored image data.
    name : str
        Human-readable layer name.
    metadata : dict[str, object]
        Mutable metadata mapping included for compatibility with code that
        expects napari layer objects.
    """

    def __init__(self, data, name: str = "image") -> None:
        """Initialize a lightweight image layer wrapper.

        Parameters
        ----------
        data : array-like
            Input image data for the benchmark case.
        name : str, optional
            Layer name exposed to the segmentation model.
        """
        self.data = data
        self.name = name
        self.metadata: dict[str, object] = {}


def main() -> int:
    """Run the command-line interface.

    Returns
    -------
    int
        Process exit code. Returns ``0`` after a successful benchmark run.
    """
    root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Benchmark 2D nuclear segmentation masks against ground truth."
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
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path.",
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=None,
        help="Optional PNG output path for the grouped summary plot.",
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


def run_benchmark(
    *,
    model_name: str,
    images_dir: Path,
    ground_truth_dir: Path,
    settings: dict[str, object],
    models_root: Path | None,
) -> list[dict[str, object]]:
    """Run a nuclear-segmentation benchmark across all matched cases.

    Parameters
    ----------
    model_name : str
        Name of the segmentation model to load.
    images_dir : pathlib.Path
        Directory containing 2D single-channel input images.
    ground_truth_dir : pathlib.Path
        Directory containing ground-truth masks matched by basename.
    settings : dict[str, object]
        Model settings forwarded directly to ``model.run(...)``.
    models_root : pathlib.Path or None
        Optional root directory for external segmentation model folders. When
        omitted, the default SenoQuant segmentation model directory is used.

    Returns
    -------
    list[dict[str, object]]
        Per-case result rows suitable for CSV export. The final row is a
        summary row with ``case_id="MEAN"`` when at least one case was run.
        When ``tqdm`` is available, progress is shown over the number of images
        processed.

    Raises
    ------
    ValueError
        Raised when a ground-truth mask is missing, when an image is not 2D,
        or when the model returns an unexpected payload.
    """
    image_paths = collect_cases(images_dir)
    ground_truth_paths = collect_cases(ground_truth_dir)
    backend = load_segmentation_backend()(models_root=models_root)
    model = backend.get_model(model_name)

    rows: list[dict[str, object]] = []
    case_items = sorted(image_paths.items())
    progress_items = iter_with_progress(
        case_items,
        description=f"Benchmarking {model_name}",
    )
    for case_id, image_path in progress_items:
        if case_id not in ground_truth_paths:
            raise ValueError(f"Missing ground truth for {case_id!r}.")

        image = load_array(image_path)
        ground_truth = load_array(ground_truth_paths[case_id])
        if image.ndim != 2 or ground_truth.ndim != 2:
            raise ValueError(f"{case_id!r} must be 2D for this benchmark.")

        result = model.run(
            task="nuclear",
            layer=ImageLayer(image),
            settings=settings,
        )
        prediction = np.asarray(result["masks"])
        row = {"case_id": case_id}
        row["model"] = model_name
        row.update(compute_case_metrics(prediction, ground_truth))
        rows.append(row)

    if rows:
        metric_names = metric_fieldnames()
        rows.append(
            {
                "case_id": "MEAN",
                "model": model_name,
                **{
                    metric_name: float(np.mean([float(row[metric_name]) for row in rows]))
                    for metric_name in metric_names
                },
                "pred_pixels": "",
                "gt_pixels": "",
            }
        )
    return rows


def iter_with_progress(
    items: list[tuple[str, Path]],
    *,
    description: str,
) -> Iterable[tuple[str, Path]]:
    """Wrap benchmark cases in a progress iterator when available.

    Parameters
    ----------
    items : list[tuple[str, pathlib.Path]]
        Sequence of benchmark cases as ``(case_id, image_path)`` pairs.
    description : str
        Progress-bar label shown alongside the current iteration state.

    Returns
    -------
    collections.abc.Iterable[tuple[str, pathlib.Path]]
        ``items`` wrapped in a ``tqdm`` progress bar when the dependency is
        available, otherwise the original list.
    """
    if tqdm is None:
        return items
    return tqdm(
        items,
        total=len(items),
        desc=description,
        unit="image",
    )


def compute_case_metrics(
    prediction,
    ground_truth,
) -> dict[str, float | int]:
    """Compute all benchmark metrics for one predicted mask.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array. Any non-zero value is treated as
        foreground.
    ground_truth : array-like
        Ground-truth label or binary mask array. Any non-zero value is treated
        as foreground.

    Returns
    -------
    dict[str, float | int]
        Mapping containing precision, recall, F1, Jaccard, Dice, and foreground
        pixel counts.
    """
    tp, fp, fn = confusion_counts(prediction, ground_truth)
    return {
        "precision": precision_score(prediction, ground_truth, counts=(tp, fp, fn)),
        "recall": recall_score(prediction, ground_truth, counts=(tp, fp, fn)),
        "f1": f1_score(prediction, ground_truth, counts=(tp, fp, fn)),
        "jaccard": jaccard_score(prediction, ground_truth, counts=(tp, fp, fn)),
        "dice": dice_score(prediction, ground_truth, counts=(tp, fp, fn)),
        "pred_pixels": int(tp + fp),
        "gt_pixels": int(tp + fn),
    }


def load_segmentation_backend():
    """Load the SenoQuant segmentation backend without importing the UI root.

    Returns
    -------
    type
        The ``SegmentationBackend`` class from
        ``senoquant.tabs.segmentation.backend``.

    Notes
    -----
    The main ``senoquant`` package imports the widget layer eagerly. This
    helper injects minimal package objects into ``sys.modules`` so the
    segmentation backend can be imported directly from ``src/senoquant``.
    """
    repo_root = Path(__file__).resolve().parents[1]
    senoquant_root = repo_root / "src" / "senoquant"

    if "senoquant" not in sys.modules:
        module = types.ModuleType("senoquant")
        module.__path__ = [str(senoquant_root)]  # type: ignore[attr-defined]
        module.__package__ = "senoquant"
        sys.modules["senoquant"] = module

    if "senoquant.tabs" not in sys.modules:
        module = types.ModuleType("senoquant.tabs")
        module.__path__ = [str(senoquant_root / "tabs")]  # type: ignore[attr-defined]
        module.__package__ = "senoquant.tabs"
        sys.modules["senoquant.tabs"] = module

    backend_module = importlib.import_module("senoquant.tabs.segmentation.backend")
    return backend_module.SegmentationBackend


def metric_fieldnames() -> list[str]:
    """Return the CSV and plot metric fields in display order.

    Returns
    -------
    list[str]
        Ordered metric names used in benchmark outputs.
    """
    return ["precision", "recall", "f1", "jaccard", "dice"]


def plot_metric_labels() -> dict[str, str]:
    """Return display labels for plotted metrics.

    Returns
    -------
    dict[str, str]
        Mapping from internal metric field names to axis labels.
    """
    return {
        "precision": "Precision",
        "recall": "Recall",
        "f1": "F1",
        "jaccard": "Jaccard",
        "dice": "Dice",
    }


def collect_cases(folder: Path) -> dict[str, Path]:
    """Collect benchmark files from a directory.

    Parameters
    ----------
    folder : pathlib.Path
        Directory containing image or ground-truth files.

    Returns
    -------
    dict[str, pathlib.Path]
        Mapping from case identifier to file path. Case identifiers are derived
        by stripping all filename suffixes.

    Raises
    ------
    FileNotFoundError
        Raised when ``folder`` does not exist.
    ValueError
        Raised when no benchmark files are found.
    """
    if not folder.exists():
        raise FileNotFoundError(f"Missing folder: {folder}")

    cases: dict[str, Path] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        case_id = strip_all_suffixes(path.name)
        cases[case_id] = path
    if not cases:
        raise ValueError(f"No files found in {folder}")
    return cases


def strip_all_suffixes(name: str) -> str:
    """Remove all suffixes from a filename.

    Parameters
    ----------
    name : str
        Filename or path-like leaf name.

    Returns
    -------
    str
        Basename with every suffix removed. For example,
        ``"sample.ome.tif"`` becomes ``"sample"``.
    """
    value = name
    while True:
        suffix = Path(value).suffix
        if not suffix:
            return value
        value = value[: -len(suffix)]


def load_settings(path: Path | None) -> dict[str, object]:
    """Load model settings from JSON.

    Parameters
    ----------
    path : pathlib.Path or None
        Path to a JSON file containing a single object. When ``None``, an empty
        settings mapping is returned.

    Returns
    -------
    dict[str, object]
        Parsed settings dictionary.

    Raises
    ------
    ValueError
        Raised when the JSON payload is not an object.
    """
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Settings JSON must contain an object.")
    return dict(payload)


def load_array(path: Path) -> np.ndarray:
    """Load an array from a supported benchmark file format.

    Parameters
    ----------
    path : pathlib.Path
        Input file path.

    Returns
    -------
    numpy.ndarray
        Loaded array data.

    Raises
    ------
    ValueError
        Raised when the file type is unsupported or an ``.npz`` archive does
        not contain exactly one array.

    Notes
    -----
    Supported file types are:

    - ``.npy``
    - ``.npz`` containing exactly one array
    - ``.tif``
    - ``.tiff``
    """
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path, allow_pickle=False)
    if suffix == ".npz":
        with np.load(path, allow_pickle=False) as payload:
            keys = list(payload.keys())
            if len(keys) != 1:
                raise ValueError(f"{path} must contain exactly one array.")
            return payload[keys[0]]
    if suffix in {".tif", ".tiff"}:
        import tifffile

        return tifffile.imread(path)
    raise ValueError(f"Unsupported file type: {path}")


def confusion_counts(prediction, ground_truth) -> tuple[int, int, int]:
    """Compute binary foreground confusion counts.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array. Any non-zero value is treated as
        foreground.
    ground_truth : array-like
        Ground-truth label or binary mask array. Any non-zero value is treated
        as foreground.

    Returns
    -------
    tuple[int, int, int]
        Foreground ``(true_positive, false_positive, false_negative)`` counts.
    """
    pred = np.asarray(prediction) > 0
    truth = np.asarray(ground_truth) > 0
    if pred.shape != truth.shape:
        raise ValueError(
            f"Prediction shape {pred.shape} does not match ground truth shape {truth.shape}."
        )
    true_positive = int(np.count_nonzero(pred & truth))
    false_positive = int(np.count_nonzero(pred & ~truth))
    false_negative = int(np.count_nonzero(~pred & truth))
    return true_positive, false_positive, false_negative


def precision_score(
    prediction,
    ground_truth,
    *,
    counts: tuple[int, int, int] | None = None,
) -> float:
    """Compute binary foreground precision.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array.
    ground_truth : array-like
        Ground-truth label or binary mask array.
    counts : tuple[int, int, int] or None, optional
        Optional precomputed ``(true_positive, false_positive, false_negative)``
        counts.

    Returns
    -------
    float
        Precision in the range ``[0, 1]``. Returns ``1.0`` when both masks are
        empty.
    """
    tp, fp, fn = counts or confusion_counts(prediction, ground_truth)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    denominator = tp + fp
    if denominator == 0:
        return 0.0
    return tp / denominator


def recall_score(
    prediction,
    ground_truth,
    *,
    counts: tuple[int, int, int] | None = None,
) -> float:
    """Compute binary foreground recall.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array.
    ground_truth : array-like
        Ground-truth label or binary mask array.
    counts : tuple[int, int, int] or None, optional
        Optional precomputed ``(true_positive, false_positive, false_negative)``
        counts.

    Returns
    -------
    float
        Recall in the range ``[0, 1]``. Returns ``1.0`` when both masks are
        empty.
    """
    tp, fp, fn = counts or confusion_counts(prediction, ground_truth)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    denominator = tp + fn
    if denominator == 0:
        return 0.0
    return tp / denominator


def f1_score(
    prediction,
    ground_truth,
    *,
    counts: tuple[int, int, int] | None = None,
) -> float:
    """Compute binary foreground F1.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array.
    ground_truth : array-like
        Ground-truth label or binary mask array.
    counts : tuple[int, int, int] or None, optional
        Optional precomputed ``(true_positive, false_positive, false_negative)``
        counts.

    Returns
    -------
    float
        F1 score in the range ``[0, 1]``. For binary foreground masks this is
        numerically identical to Dice.
    """
    tp, fp, fn = counts or confusion_counts(prediction, ground_truth)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    precision = precision_score(prediction, ground_truth, counts=(tp, fp, fn))
    recall = recall_score(prediction, ground_truth, counts=(tp, fp, fn))
    denominator = precision + recall
    if denominator == 0.0:
        return 0.0
    return (2.0 * precision * recall) / denominator


def jaccard_score(
    prediction,
    ground_truth,
    *,
    counts: tuple[int, int, int] | None = None,
) -> float:
    """Compute binary foreground Jaccard index.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array.
    ground_truth : array-like
        Ground-truth label or binary mask array.
    counts : tuple[int, int, int] or None, optional
        Optional precomputed ``(true_positive, false_positive, false_negative)``
        counts.

    Returns
    -------
    float
        Jaccard index in the range ``[0, 1]``. Returns ``1.0`` when both masks
        are empty.
    """
    tp, fp, fn = counts or confusion_counts(prediction, ground_truth)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    denominator = tp + fp + fn
    if denominator == 0:
        return 0.0
    return tp / denominator


def dice_score(
    prediction,
    ground_truth,
    *,
    counts: tuple[int, int, int] | None = None,
) -> float:
    """Compute the binary Dice score between two masks.

    Parameters
    ----------
    prediction : array-like
        Predicted label or binary mask array.
    ground_truth : array-like
        Ground-truth label or binary mask array.
    counts : tuple[int, int, int] or None, optional
        Optional precomputed ``(true_positive, false_positive, false_negative)``
        counts.

    Returns
    -------
    float
        Dice similarity coefficient in the range ``[0, 1]``. Returns ``1.0``
        when both masks are empty.
    """
    tp, fp, fn = counts or confusion_counts(prediction, ground_truth)
    if tp == 0 and fp == 0 and fn == 0:
        return 1.0
    denominator = (2 * tp) + fp + fn
    if denominator == 0:
        return 0.0
    return (2 * tp) / denominator


def read_mean_rows(csv_paths: Iterable[Path]) -> dict[str, dict[str, float]]:
    """Read mean metric rows from benchmark CSV files.

    Parameters
    ----------
    csv_paths : iterable of pathlib.Path
        CSV files generated by this benchmark script.

    Returns
    -------
    dict[str, dict[str, float]]
        Mapping from model name to mean metric values.
    """
    metric_names = metric_fieldnames()
    summaries: dict[str, dict[str, float]] = {}
    for csv_path in sorted(csv_paths):
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            mean_row: dict[str, str] | None = None
            for row in reader:
                if row.get("case_id") == "MEAN":
                    mean_row = row
            if mean_row is None:
                continue
        if any(metric_name not in mean_row for metric_name in metric_names):
            continue
        model_name = mean_row.get("model", "").strip() or csv_path.stem
        summaries[model_name] = {
            metric_name: float(mean_row[metric_name])
            for metric_name in metric_names
        }
    return summaries


def write_summary_plot(
    *,
    csv_dir: Path,
    plot_path: Path,
    title: str,
) -> None:
    """Write a grouped bar chart summarizing all benchmark CSVs in a folder.

    Parameters
    ----------
    csv_dir : pathlib.Path
        Directory containing benchmark CSV files.
    plot_path : pathlib.Path
        Output path for the PNG chart.
    title : str
        Plot title.

    Notes
    -----
    The plot summarizes the ``MEAN`` rows from all compatible ``.csv`` files in
    ``csv_dir``. This makes it easy to re-run the benchmark for multiple models
    and keep one comparison chart that resembles the grouped metric plot in the
    example image.
    """
    configure_matplotlib_cache()
    import matplotlib.pyplot as plt

    csv_paths = [
        path
        for path in sorted(csv_dir.glob("*.csv"))
        if path.is_file() and not path.name.startswith(".")
    ]
    summaries = read_mean_rows(csv_paths)
    if not summaries:
        raise ValueError(f"No benchmark CSV files found in {csv_dir}")

    metric_names = metric_fieldnames()
    label_map = plot_metric_labels()
    x_positions = np.arange(len(metric_names), dtype=float)
    model_names = list(summaries)
    model_count = len(model_names)
    bar_width = 0.8 / max(model_count, 1)

    fig, ax = plt.subplots(figsize=(16, 12))
    for index, model_name in enumerate(model_names):
        offset = (index - ((model_count - 1) / 2.0)) * bar_width
        values = [summaries[model_name][metric_name] for metric_name in metric_names]
        bars = ax.bar(
            x_positions + offset,
            values,
            width=bar_width,
            label=model_name,
        )
        for bar, value in zip(bars, values, strict=True):
            ax.text(
                bar.get_x() + (bar.get_width() / 2.0),
                min(value + 0.01, 1.02),
                format_metric_value(value),
                ha="center",
                va="bottom",
                fontsize=11,
            )

    ax.set_xticks(x_positions)
    ax.set_xticklabels([label_map[name] for name in metric_names])
    ax.set_ylim(0.0, 1.04)
    ax.set_ylabel("Evaluation Index")
    ax.set_title(title)
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=200)
    plt.close(fig)


def format_metric_value(value: float) -> str:
    """Format a metric value for bar annotations.

    Parameters
    ----------
    value : float
        Metric value to format.

    Returns
    -------
    str
        Compact decimal string with trailing zeros removed.
    """
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted or "0"


def configure_matplotlib_cache() -> None:
    """Point matplotlib at a writable cache directory when needed.

    Notes
    -----
    In some terminal or sandboxed environments the default matplotlib cache
    directories under the home folder are not writable. Setting these
    environment variables before importing matplotlib avoids noisy warnings and
    repeated font-cache rebuilds.
    """
    cache_root = Path(tempfile.gettempdir()) / "senoquant-matplotlib-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write benchmark rows to CSV.

    Parameters
    ----------
    path : pathlib.Path
        Output CSV path.
    rows : list[dict[str, object]]
        Benchmark rows returned by :func:`run_benchmark`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "model",
                *metric_fieldnames(),
                "pred_pixels",
                "gt_pixels",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
