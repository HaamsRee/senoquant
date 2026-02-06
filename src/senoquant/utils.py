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
