"""Benchmark execution for SenoQuant segmentation models."""

from __future__ import annotations

import importlib
import sys
import types
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from .data import collect_cases, load_array
from .matching import (
    DEFAULT_IOU_THRESHOLDS,
    aggregate_dataset_metrics,
    compute_instance_metrics,
    parse_iou_thresholds,
)
from .results import make_case_row, make_dataset_summary_row

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover - optional dependency
    tqdm = None


class ImageLayer:
    """Minimal napari-like image layer used by the benchmark runner."""

    def __init__(self, data, name: str = "image") -> None:
        self.data = data
        self.name = name
        self.metadata: dict[str, object] = {}


def run_benchmark(
    *,
    model_name: str,
    images_dir: Path,
    ground_truth_dir: Path,
    settings: dict[str, object],
    models_root: Path | None,
    iou_thresholds: Iterable[float] = DEFAULT_IOU_THRESHOLDS,
) -> list[dict[str, object]]:
    """Run a nuclear-segmentation benchmark across all matched cases."""
    thresholds = parse_iou_thresholds(iou_thresholds)
    image_paths = collect_cases(images_dir)
    ground_truth_paths = collect_cases(ground_truth_dir)
    backend = load_segmentation_backend()(models_root=models_root)
    model = backend.get_model(model_name)

    rows: list[dict[str, object]] = []
    per_threshold_metrics = defaultdict(list)
    case_items = sorted(image_paths.items())
    progress_items = iter_with_progress(case_items, description=f"Benchmarking {model_name}")

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
        if not isinstance(result, dict) or "masks" not in result:
            raise ValueError(
                f"Model {model_name!r} must return a mapping with a 'masks' entry."
            )

        prediction = np.asarray(result["masks"])
        for metrics in compute_instance_metrics(
            prediction,
            ground_truth,
            iou_thresholds=thresholds,
        ):
            rows.append(
                make_case_row(
                    case_id=case_id,
                    model_name=model_name,
                    metrics=metrics,
                )
            )
            per_threshold_metrics[metrics.iou_threshold].append(metrics)

    for threshold in thresholds:
        summary_metrics = aggregate_dataset_metrics(per_threshold_metrics[threshold])
        rows.append(
            make_dataset_summary_row(
                model_name=model_name,
                metrics=summary_metrics,
            )
        )
    return rows


def iter_with_progress(
    items: list[tuple[str, Path]],
    *,
    description: str,
) -> Iterable[tuple[str, Path]]:
    """Wrap benchmark cases in a progress iterator when available."""
    if tqdm is None:
        return items
    return tqdm(items, total=len(items), desc=description, unit="image")


def load_segmentation_backend():
    """Load the SenoQuant segmentation backend without importing the UI root."""
    repo_root = Path(__file__).resolve().parents[2]
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
