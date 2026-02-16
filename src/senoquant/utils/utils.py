"""Shared utility helpers for SenoQuant."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import numpy as np


def layer_data_asarray(layer, *, squeeze: bool = True) -> np.ndarray:
    """Return layer data as a NumPy array, optionally squeezed.

    Parameters
    ----------
    layer : object
        napari layer instance providing a ``data`` attribute.
    squeeze : bool, optional
        Whether to remove singleton dimensions.

    Returns
    -------
    numpy.ndarray
        Array representation of the layer data.
    """
    data = getattr(layer, "data", None)
    data = np.asarray(data)
    return np.squeeze(data) if squeeze else data


def _label_chunks(shape: tuple[int, ...], *, tile_xy: int = 512) -> tuple[int, ...]:
    """Return chunk sizes tuned for label-like 2D/3D arrays."""
    if len(shape) == 0:
        return ()
    if len(shape) == 1:
        return (min(shape[0], tile_xy),)
    if len(shape) == 2:
        return (min(shape[0], tile_xy), min(shape[1], tile_xy))
    leading = tuple(1 for _ in shape[:-2])
    return leading + (min(shape[-2], tile_xy), min(shape[-1], tile_xy))


def labels_data_as_dask(data):
    """Wrap label data in a chunked dask array when possible.

    Parameters
    ----------
    data : array-like
        Label data to present in napari.

    Returns
    -------
    array-like
        Dask-backed array when conversion succeeds, otherwise the original
        array-like input.
    """
    if data is None:
        return None

    try:
        import dask.array as da
    except Exception:
        return data

    if isinstance(data, da.Array):
        return data

    array = data if isinstance(data, np.ndarray) else np.asarray(data)
    if array.ndim == 0 or array.size == 0:
        return array

    return da.from_array(array, chunks=_label_chunks(array.shape))


def append_run_metadata(
    metadata: dict | None,
    *,
    task: str,
    runner_type: str,
    runner_name: str,
    settings: dict | None = None,
) -> dict:
    """Append a timestamped run entry to layer metadata.

    Parameters
    ----------
    metadata : dict or None
        Existing layer metadata.
    task : str
        Task name (for example ``"nuclear"``).
    runner_type : str
        Run source type (for example ``"segmentation_model"``).
    runner_name : str
        Model or detector name used for the run.
    settings : dict or None, optional
        Settings used for the run.

    Returns
    -------
    dict
        Updated metadata dictionary containing ``task`` and ``run_history``.
    """
    payload: dict[str, object] = {}
    if isinstance(metadata, dict):
        payload.update(metadata)

    history: list[dict[str, object]] = []
    raw_history = payload.get("run_history")
    if isinstance(raw_history, list):
        for item in raw_history:
            if isinstance(item, dict):
                history.append(dict(item))

    run_entry = {
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "task": task,
        "runner_type": runner_type,
        "runner_name": runner_name,
        "settings": deepcopy(settings) if isinstance(settings, dict) else {},
    }
    history.append(run_entry)

    payload["task"] = task
    payload["run_history"] = history
    return payload
