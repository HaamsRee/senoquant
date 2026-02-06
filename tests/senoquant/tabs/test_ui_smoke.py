"""Smoke tests for Qt-based frontends.

Notes
-----
These tests instantiate frontend widgets with stubbed Qt classes to
validate basic wiring and helper behaviors.
"""

from __future__ import annotations

import numpy as np

from tests.conftest import DummyLayer, DummyViewer
from senoquant._widget import SenoQuantWidget
from senoquant.tabs.batch.frontend import BatchTab
from senoquant.tabs.quantification.frontend import QuantificationTab
from senoquant.tabs.segmentation.frontend import SegmentationTab
from senoquant.tabs.settings.backend import SettingsBackend
from senoquant.tabs.settings.frontend import SettingsTab
from senoquant.tabs.spots.frontend import SpotsTab


def test_settings_tab_instantiates() -> None:
    """Instantiate the settings tab UI.

    Returns
    -------
    None
    """
    tab = SettingsTab()
    assert hasattr(tab, "_preload_checkbox")


def test_segmentation_tab_validation() -> None:
    """Validate single-channel layer checks.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    settings = SettingsBackend()
    settings.set_preload_models(False)
    tab = SegmentationTab(napari_viewer=viewer, settings_backend=settings)
    layer = DummyLayer(np.zeros((4, 4)), "img", rgb=False)
    assert tab._validate_single_channel_layer(layer, "Layer") is True
    rgb_layer = DummyLayer(np.zeros((4, 4, 3)), "rgb", rgb=True)
    assert tab._validate_single_channel_layer(rgb_layer, "Layer") is False


def test_segmentation_labels_include_task_metadata() -> None:
    """Tag generated segmentation labels with task metadata."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    settings = SettingsBackend()
    settings.set_preload_models(False)
    tab = SegmentationTab(napari_viewer=viewer, settings_backend=settings)
    source = DummyLayer(np.zeros((4, 4)), "img", metadata={"path": "file.tif"})

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "model",
        "nuc",
        settings={"threshold": 0.2},
    )
    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "model",
        "cyto",
        settings={"radius": 5},
    )

    nuc_layer = viewer.layers["img_model_nuc_labels"]
    cyto_layer = viewer.layers["img_model_cyto_labels"]
    assert nuc_layer.metadata.get("task") == "nuclear"
    assert cyto_layer.metadata.get("task") == "cytoplasmic"
    assert nuc_layer.metadata.get("path") == "file.tif"
    assert nuc_layer.metadata["run_history"][-1]["runner_name"] == "model"
    assert cyto_layer.metadata["run_history"][-1]["settings"] == {"radius": 5}


def test_segmentation_labels_metadata_without_name_lookup() -> None:
    """Populate metadata even when viewer renames duplicate labels."""

    class _SanitizingViewer(DummyViewer):
        def add_labels(self, data, name: str, metadata=None):
            layer = DummyLayer(np.asarray(data), f"{name}_1", metadata=metadata or {})
            self.layers.append(layer)
            return layer

    viewer = _SanitizingViewer([DummyLayer(np.zeros((4, 4)), "img")])
    settings = SettingsBackend()
    settings.set_preload_models(False)
    tab = SegmentationTab(napari_viewer=viewer, settings_backend=settings)
    source = DummyLayer(np.zeros((4, 4)), "img", metadata={"path": "file.tif"})

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "model", "nuc")

    labels_layer = viewer.layers[-1]
    assert labels_layer.name == "img_model_nuc_labels_1"
    assert labels_layer.metadata.get("task") == "nuclear"
    assert labels_layer.metadata.get("path") == "file.tif"


def test_segmentation_labels_preserve_source_run_history() -> None:
    """Keep source run history and append current model settings."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    settings = SettingsBackend()
    settings.set_preload_models(False)
    tab = SegmentationTab(napari_viewer=viewer, settings_backend=settings)
    source = DummyLayer(
        np.zeros((4, 4)),
        "img",
        metadata={
            "task": "nuclear",
            "run_history": [
                {
                    "timestamp": "2026-02-06T00:00:00.000Z",
                    "task": "nuclear",
                    "runner_type": "segmentation_model",
                    "runner_name": "default_2d",
                    "settings": {"threshold": 0.3},
                }
            ],
        },
    )

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "nuclear_dilation",
        "cyto",
        settings={"radius": 7},
    )

    labels_layer = viewer.layers["img_nuclear_dilation_cyto_labels"]
    history = labels_layer.metadata["run_history"]
    assert labels_layer.metadata.get("task") == "cytoplasmic"
    assert len(history) == 2
    assert history[0]["runner_name"] == "default_2d"
    assert history[-1]["runner_name"] == "nuclear_dilation"
    assert history[-1]["settings"] == {"radius": 7}


def test_spots_tab_instantiates() -> None:
    """Instantiate the spots tab UI.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SpotsTab(napari_viewer=viewer)
    assert hasattr(tab, "_detector_combo")


def test_quantification_tab_instantiates() -> None:
    """Instantiate the quantification tab UI.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = QuantificationTab(
        napari_viewer=viewer,
        show_output_section=False,
        show_process_button=False,
    )
    assert hasattr(tab, "_feature_registry")


def test_batch_tab_instantiates() -> None:
    """Instantiate the batch tab UI.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = BatchTab(napari_viewer=viewer)
    assert hasattr(tab, "_backend")


def test_main_widget_instantiates() -> None:
    """Instantiate the main SenoQuant widget.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    widget = SenoQuantWidget(viewer)
    assert widget is not None
