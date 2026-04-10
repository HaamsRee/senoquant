"""Simplified instance matching for label images."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from skimage.measure import label

DEFAULT_IOU_THRESHOLDS: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
COUNT_FIELDS: tuple[str, ...] = (
    "n_true",
    "n_pred",
    "tp",
    "fp",
    "fn",
)
METRIC_FIELDS: tuple[str, ...] = (
    "precision",
    "recall",
    "jaccard",
    "dice",
)
CSV_VALUE_FIELDS: tuple[str, ...] = (*COUNT_FIELDS, *METRIC_FIELDS)
PLOT_METRIC_FIELDS: tuple[str, ...] = METRIC_FIELDS
PLOT_METRIC_LABELS: dict[str, str] = {
    "precision": "Precision",
    "recall": "Recall",
    "jaccard": "Jaccard",
    "dice": "Dice",
}


@dataclass(frozen=True, slots=True)
class InstanceMetrics:
    """Instance metrics for one IoU threshold."""

    criterion: str
    iou_threshold: float
    n_true: int
    n_pred: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    jaccard: float
    dice: float


def parse_iou_thresholds(values: Iterable[float]) -> tuple[float, ...]:
    """Validate and normalize IoU thresholds."""
    thresholds = tuple(sorted({float(value) for value in values}))
    if not thresholds:
        raise ValueError("At least one IoU threshold is required.")
    for threshold in thresholds:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"IoU thresholds must be in the range [0, 1]. Got {threshold}."
            )
    return thresholds


def compute_instance_metrics(
    prediction,
    ground_truth,
    *,
    iou_thresholds: Iterable[float],
) -> list[InstanceMetrics]:
    """Match predicted and ground-truth instances across IoU thresholds."""
    thresholds = parse_iou_thresholds(iou_thresholds)
    truth = _prepare_label_image(ground_truth, name="ground_truth")
    pred = _prepare_label_image(prediction, name="prediction")
    if truth.shape != pred.shape:
        raise ValueError(
            f"Prediction shape {pred.shape} does not match ground truth shape {truth.shape}."
        )

    overlap = _label_overlap(truth, pred)
    scores = _intersection_over_union(overlap)[1:, 1:]
    n_true, n_pred = scores.shape
    n_matched = min(n_true, n_pred)

    metrics: list[InstanceMetrics] = []
    for threshold in thresholds:
        metrics.append(
            _match_at_threshold(
                scores=scores,
                threshold=threshold,
                n_true=n_true,
                n_pred=n_pred,
                n_matched=n_matched,
            )
        )
    return metrics


def aggregate_dataset_metrics(metrics: Iterable[InstanceMetrics]) -> InstanceMetrics:
    """Aggregate case-level metrics into dataset-level instance metrics."""
    metric_list = list(metrics)
    if not metric_list:
        raise ValueError("Cannot aggregate an empty metric list.")

    first = metric_list[0]
    for metric in metric_list[1:]:
        if metric.criterion != first.criterion:
            raise ValueError("All metrics must use the same matching criterion.")
        if metric.iou_threshold != first.iou_threshold:
            raise ValueError("All metrics must use the same IoU threshold.")

    n_true = sum(metric.n_true for metric in metric_list)
    n_pred = sum(metric.n_pred for metric in metric_list)
    tp = sum(metric.tp for metric in metric_list)
    fp = sum(metric.fp for metric in metric_list)
    fn = sum(metric.fn for metric in metric_list)
    return _build_metrics(
        criterion=first.criterion,
        threshold=first.iou_threshold,
        n_true=n_true,
        n_pred=n_pred,
        tp=tp,
        fp=fp,
        fn=fn,
    )


def _prepare_label_image(array, *, name: str) -> np.ndarray:
    """Normalize a binary or label image into sequential instance labels."""
    labels = np.asarray(array)
    if labels.ndim < 1:
        raise ValueError(f"{name} must be an array.")
    if not (
        np.issubdtype(labels.dtype, np.bool_)
        or np.issubdtype(labels.dtype, np.integer)
    ):
        raise ValueError(f"{name} must contain boolean or integer labels.")
    if labels.size == 0:
        return labels.astype(np.int32, copy=False)

    labels = labels.astype(np.int64, copy=False)
    if np.any(labels < 0):
        raise ValueError(f"{name} must contain non-negative labels.")

    unique_labels = np.unique(labels)
    if unique_labels.size <= 2 and set(unique_labels.tolist()).issubset({0, 1}):
        labels = label(labels > 0)
    return _relabel_sequential(labels)


def _relabel_sequential(labels: np.ndarray) -> np.ndarray:
    """Relabel positive integers to ``1..N`` while keeping background at ``0``."""
    if labels.size == 0:
        return labels.astype(np.int32, copy=False)

    positive = np.unique(labels[labels > 0])
    sequential = np.zeros(labels.shape, dtype=np.int32)
    if positive.size == 0:
        return sequential

    mask = labels > 0
    sequential[mask] = np.searchsorted(positive, labels[mask]) + 1
    return sequential


def _label_overlap(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """Count pixel overlap between sequential ground-truth and predicted labels."""
    n_true = int(y_true.max())
    n_pred = int(y_pred.max())
    flat_index = y_true.ravel() * (n_pred + 1) + y_pred.ravel()
    counts = np.bincount(flat_index, minlength=(n_true + 1) * (n_pred + 1))
    return counts.reshape((n_true + 1, n_pred + 1))


def _intersection_over_union(overlap: np.ndarray) -> np.ndarray:
    """Convert an overlap matrix into an IoU matrix."""
    if overlap.size == 0 or int(np.sum(overlap)) == 0:
        return overlap.astype(np.float32, copy=False)

    pred_pixels = np.sum(overlap, axis=0, keepdims=True)
    true_pixels = np.sum(overlap, axis=1, keepdims=True)
    denominator = pred_pixels + true_pixels - overlap
    scores = np.zeros(overlap.shape, dtype=np.float32)
    np.divide(overlap, denominator, out=scores, where=denominator > 0)
    return scores


def _match_at_threshold(
    *,
    scores: np.ndarray,
    threshold: float,
    n_true: int,
    n_pred: int,
    n_matched: int,
) -> InstanceMetrics:
    """Compute metrics for one IoU threshold."""
    if n_matched == 0:
        return _build_metrics(
            criterion="iou",
            threshold=threshold,
            n_true=n_true,
            n_pred=n_pred,
            tp=0,
            fp=n_pred,
            fn=n_true,
        )

    costs = -(scores >= threshold).astype(float) - (scores / (2.0 * n_matched))
    true_index, pred_index = linear_sum_assignment(costs)
    matched_scores = scores[true_index, pred_index]
    matched_mask = matched_scores >= threshold
    tp = int(np.count_nonzero(matched_mask))
    fp = int(n_pred - tp)
    fn = int(n_true - tp)
    return _build_metrics(
        criterion="iou",
        threshold=threshold,
        n_true=n_true,
        n_pred=n_pred,
        tp=tp,
        fp=fp,
        fn=fn,
    )


def _build_metrics(
    *,
    criterion: str,
    threshold: float,
    n_true: int,
    n_pred: int,
    tp: int,
    fp: int,
    fn: int,
) -> InstanceMetrics:
    """Construct an :class:`InstanceMetrics` object from accumulated counts."""
    return InstanceMetrics(
        criterion=criterion,
        iou_threshold=threshold,
        n_true=n_true,
        n_pred=n_pred,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=_precision(tp, fp),
        recall=_recall(tp, fn),
        jaccard=_jaccard(tp, fp, fn),
        dice=_dice(tp, fp, fn),
    )


def _safe_divide(numerator: float, denominator: float) -> float:
    """Return ``0.0`` when the denominator is zero."""
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def _precision(tp: int, fp: int) -> float:
    """Instance precision."""
    return _safe_divide(tp, tp + fp) if tp > 0 else 0.0


def _recall(tp: int, fn: int) -> float:
    """Instance recall."""
    return _safe_divide(tp, tp + fn) if tp > 0 else 0.0


def _jaccard(tp: int, fp: int, fn: int) -> float:
    """Instance Jaccard index derived from matched object counts."""
    return _safe_divide(tp, tp + fp + fn) if tp > 0 else 0.0


def _dice(tp: int, fp: int, fn: int) -> float:
    """Instance Dice score derived from matched object counts."""
    return _safe_divide(2 * tp, (2 * tp) + fp + fn) if tp > 0 else 0.0
