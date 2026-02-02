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

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "model", "nuc")
    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "model", "cyto")

    nuc_layer = viewer.layers["img_model_nuc_labels"]
    cyto_layer = viewer.layers["img_model_cyto_labels"]
    assert nuc_layer.metadata.get("task") == "nuclear"
    assert cyto_layer.metadata.get("task") == "cytoplasmic"
    assert nuc_layer.metadata.get("path") == "file.tif"


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
