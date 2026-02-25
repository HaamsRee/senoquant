"""Helpers for efficient label-wise morphological operations."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
from scipy import ndimage as ndi

_SPARSE_LABEL_RATIO = 4


def _pad_slices(
    slices: tuple[slice, ...],
    shape: tuple[int, ...],
    pad: int,
) -> tuple[slice, ...]:
    """Expand slices symmetrically while staying within array bounds."""
    return tuple(
        slice(
            max(0, axis_slice.start - pad),
            min(shape[axis], axis_slice.stop + pad),
        )
        for axis, axis_slice in enumerate(slices)
    )


def _iter_direct_label_slices(
    labels: np.ndarray,
    label_ids: np.ndarray,
) -> Iterator[tuple[int, tuple[slice, ...]]]:
    """Yield slices directly from input labels when ids are near-dense."""
    max_label = int(label_ids[-1])
    objects = ndi.find_objects(labels, max_label=max_label)
    for label_id in label_ids:
        label_index = int(label_id) - 1
        if label_index < 0 or label_index >= len(objects):
            continue
        slices = objects[label_index]
        if slices is None:
            continue
        yield int(label_id), slices


def _iter_sparse_label_slices(
    labels: np.ndarray,
    label_ids: np.ndarray,
) -> Iterator[tuple[int, tuple[slice, ...]]]:
    """Yield slices via dense remapping for sparse/non-sequential label ids."""
    dense_labels = np.zeros_like(labels, dtype=np.int32)
    nonzero = labels > 0
    dense_labels[nonzero] = (
        np.searchsorted(label_ids, labels[nonzero]).astype(np.int32) + 1
    )
    objects = ndi.find_objects(dense_labels, max_label=int(label_ids.size))
    for dense_id, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        yield int(label_ids[dense_id - 1]), slices


def iter_label_regions(
    labels: np.ndarray,
    *,
    pad: int,
) -> Iterator[tuple[int, tuple[slice, ...], np.ndarray]]:
    """Yield padded binary regions for each non-zero label id.

    Parameters
    ----------
    labels : numpy.ndarray
        Input label image.
    pad : int
        Padding (in pixels/voxels) added to each label's bounding box.

    Yields
    ------
    tuple
        ``(label_id, padded_slices, mask)`` where ``mask`` is a boolean array
        for the current label within the padded crop.
    """
    label_ids = np.unique(labels)
    label_ids = label_ids[label_ids > 0]
    if label_ids.size == 0:
        return

    max_label = int(label_ids[-1])
    if max_label <= int(label_ids.size) * _SPARSE_LABEL_RATIO:
        slice_iter = _iter_direct_label_slices(labels, label_ids)
    else:
        slice_iter = _iter_sparse_label_slices(labels, label_ids)

    for label_id, slices in slice_iter:
        padded_slices = _pad_slices(slices, labels.shape, pad)
        region = labels[padded_slices]
        yield label_id, padded_slices, region == label_id
