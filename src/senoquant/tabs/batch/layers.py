"""Lightweight layer shims used for batch processing."""

from __future__ import annotations

from typing import Iterable

import numpy as np

class Image:
    """Lightweight image layer placeholder."""

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
    """Lightweight labels layer placeholder."""

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
    """Minimal viewer shim exposing layers for export routines."""

    def __init__(self, layers: Iterable[object] | None = None) -> None:
        self.layers = list(layers) if layers is not None else []

    def set_layers(self, layers: Iterable[object]) -> None:
        self.layers = list(layers)
