"""Shared utility helpers for SenoQuant."""

from __future__ import annotations

import numpy as np


def layer_data_asarray(layer, *, squeeze: bool = True) -> np.ndarray:
    """Return layer data as a NumPy array, optionally squeezed.

    Parameters
    ----------
    layer : object
        Napari layer instance providing a ``data`` attribute.
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
