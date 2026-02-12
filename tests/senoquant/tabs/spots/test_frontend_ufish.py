"""Tests for spots frontend integration helpers."""

from __future__ import annotations

import dask.array as da
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

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "detector",
        settings={"threshold": 0.4},
    )

    labels_layer = viewer.layers["img_detector_spot_labels"]
    assert labels_layer.metadata.get("task") == "spots"
    assert labels_layer.metadata.get("path") == "file.tif"
    assert labels_layer.metadata["run_history"][-1]["runner_name"] == "detector"
    assert labels_layer.metadata["run_history"][-1]["settings"] == {
        "threshold": 0.4
    }


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

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "detector",
        settings={"threshold": 0.4},
    )

    labels_layer = viewer.layers[-1]
    assert labels_layer.name == "img_detector_spot_labels_1"
    assert labels_layer.metadata.get("task") == "spots"
    assert labels_layer.metadata.get("path") == "file.tif"
    assert labels_layer.metadata["run_history"][-1]["runner_type"] == "spot_detector"


def test_spot_labels_are_added_as_dask_arrays() -> None:
    """Wrap detector masks as dask arrays, then materialize layer data."""

    class _RawLayer:
        def __init__(self, data, name: str, metadata=None):
            self.data = data
            self.name = name
            self.metadata = metadata or {}
            self.contour = None

    class _CaptureViewer(DummyViewer):
        def __init__(self, layers):
            super().__init__(layers)
            self.received = None

        def add_labels(self, data, name: str, metadata=None):
            self.received = data
            layer = _RawLayer(data, name, metadata=metadata or {})
            self.layers.append(layer)
            return layer

    viewer = _CaptureViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = spots_frontend.SpotsTab(napari_viewer=viewer)
    source = Image(np.zeros((4, 4), dtype=np.float32), "img")

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "detector",
        settings={"threshold": 0.4},
    )

    assert isinstance(viewer.received, da.Array)
    assert isinstance(viewer.layers[-1].data, np.ndarray)


def test_handle_run_result_adds_size_filter_to_run_settings() -> None:
    """Persist current diameter filter values in spot run metadata settings."""
    viewer = DummyViewer([Image(np.zeros((4, 4), dtype=np.float32), "img")])
    tab = spots_frontend.SpotsTab(napari_viewer=viewer)
    source_layer = viewer.layers["img"]

    assert tab._min_size_spin is not None
    assert tab._max_size_spin is not None
    tab._min_size_spin.setValue(3)
    tab._max_size_spin.setValue(9)

    tab._handle_run_result(
        source_layer,
        "detector",
        {"threshold": 0.4},
        {"mask": np.ones((4, 4), dtype=np.uint16)},
    )

    labels_layer = viewer.layers["img_detector_spot_labels"]
    settings = labels_layer.metadata["run_history"][-1]["settings"]
    assert settings["threshold"] == 0.4
    assert settings["size_filter"] == {
        "min_size": 3,
        "max_size": 9,
    }
