"""Lightweight layer shims used for batch processing.

These classes emulate the minimal attributes used by feature exporters
and quantification routines, without requiring a live napari viewer.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np

class Image:
    """Lightweight image layer placeholder.

    Parameters
    ----------
    data : numpy.ndarray or None
        Image data array.
    name : str
        Layer name.
    metadata : dict or None, optional
        Metadata dictionary (e.g., pixel sizes).
    rgb : bool, optional
        Whether the layer should be treated as RGB.
    """

    def __init__(
        self,
        data: np.ndarray | None,
        name: str,
        metadata: dict | None = None,
        rgb: bool = False,
    ) -> None:
        self.data = data
        self.name = name
        self.metadata = metadata or {}
        self.rgb = rgb


class Labels:
    """Lightweight labels layer placeholder.

    Parameters
    ----------
    data : numpy.ndarray or None
        Label image data.
    name : str
        Layer name.
    metadata : dict or None, optional
        Metadata dictionary (e.g., pixel sizes).
    """

    def __init__(
        self,
        data: np.ndarray | None,
        name: str,
        metadata: dict | None = None,
    ) -> None:
        self.data = data
        self.name = name
        self.metadata = metadata or {}


class BatchViewer:
    """Minimal viewer shim exposing layers for export routines.

    Parameters
    ----------
    layers : iterable of object or None, optional
        Initial layer collection.
    """

    def __init__(self, layers: Iterable[object] | None = None) -> None:
        """Initialize the viewer shim."""
        self.layers = list(layers) if layers is not None else []

    def set_layers(self, layers: Iterable[object]) -> None:
        """Replace the current layer collection.

        Parameters
        ----------
        layers : iterable of object
            New layer collection.
        """
        self.layers = list(layers)
