"""Tests for spots frontend integration helpers."""

from __future__ import annotations

import numpy as np

from tests.conftest import DummyViewer, Image, Labels
from senoquant.tabs.spots import frontend as spots_frontend

# ruff: noqa: EM101, S101, SLF001, TRY003


def test_spot_labels_include_task_metadata() -> None:
    """Tag generated spot labels with task metadata."""
    viewer = DummyViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = spots_frontend.SpotsTab(napari_viewer=viewer)
    source = Image(
        np.zeros((4, 4), dtype=np.float32),
        "img",
        metadata={"path": "file.tif"},
    )

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "detector")

    labels_layer = viewer.layers["img_detector_spot_labels"]
    assert labels_layer.metadata.get("task") == "spots"
    assert labels_layer.metadata.get("path") == "file.tif"


def test_spot_labels_metadata_without_name_lookup() -> None:
    """Populate metadata even when viewer sanitizes labels names."""

    class _SanitizingViewer(DummyViewer):
        def add_labels(self, data, name: str, metadata=None):
            layer = Labels(np.asarray(data), f"{name}_1", metadata=metadata or {})
            layer.contour = None
            self.layers.append(layer)
            return layer

    viewer = _SanitizingViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = spots_frontend.SpotsTab(napari_viewer=viewer)
    source = Image(
        np.zeros((4, 4), dtype=np.float32),
        "img",
        metadata={"path": "file.tif"},
    )

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "detector")

    labels_layer = viewer.layers[-1]
    assert labels_layer.name == "img_detector_spot_labels_1"
    assert labels_layer.metadata.get("task") == "spots"
    assert labels_layer.metadata.get("path") == "file.tif"
