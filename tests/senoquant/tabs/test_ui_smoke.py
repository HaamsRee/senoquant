"""Smoke tests for Qt-based frontends.

Notes
-----
These tests instantiate frontend widgets with stubbed Qt classes to
validate basic wiring and helper behaviors.
"""

from __future__ import annotations

import dask.array as da
import numpy as np

from tests.conftest import DummyLayer, DummyViewer
from senoquant._widget import SenoQuantWidget
from senoquant.tabs.batch.frontend import BatchTab
from senoquant.tabs.quantification.frontend import QuantificationTab
from senoquant.tabs.segmentation.frontend import SegmentationTab
from senoquant.tabs.settings.frontend import SettingsTab
from senoquant.tabs.spots.frontend import SpotsTab


class _DummySegmentationModel:
    """Minimal segmentation model stub for UI smoke tests."""

    def supports_task(self, _task: str) -> bool:
        return True

    def list_settings(self) -> list[dict]:
        return [
            {
                "key": "threshold",
                "label": "Threshold",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": 0.1,
                "decimals": 2,
            },
            {
                "key": "enabled",
                "label": "Enabled",
                "type": "bool",
                "default": False,
            },
        ]

    def cytoplasmic_input_modes(self) -> list[str]:
        return ["cytoplasmic"]

    def cytoplasmic_nuclear_optional(self) -> bool:
        return True


class _DummySegmentationBackend:
    """Minimal segmentation backend stub for UI smoke tests."""

    def __init__(self) -> None:
        self._model = _DummySegmentationModel()
        self.preloaded = False

    def list_model_names(self, task: str | None = None) -> list[str]:
        if task in {"nuclear", "cytoplasmic", None}:
            return ["dummy_model"]
        return []

    def get_model(self, _name: str) -> _DummySegmentationModel:
        return self._model

    def get_preloaded_model(self, _name: str) -> _DummySegmentationModel:
        return self._model

    def preload_models(self) -> None:
        self.preloaded = True


class _DummyDetector:
    """Minimal spot detector stub for UI smoke tests."""

    def list_settings(self) -> list[dict]:
        return [
            {
                "key": "threshold",
                "label": "Threshold",
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "default": 0.2,
                "decimals": 2,
            }
        ]


class _DummySpotsBackend:
    """Minimal spots backend stub for UI smoke tests."""

    def __init__(self) -> None:
        self._detector = _DummyDetector()

    def list_detector_names(self) -> list[str]:
        return ["dummy_detector"]

    def get_detector(self, _name: str) -> _DummyDetector:
        return self._detector


def test_settings_tab_instantiates() -> None:
    """Instantiate the settings tab UI.

    Returns
    -------
    None
    """
    tab = SettingsTab()
    assert hasattr(tab, "_save_button")
    assert hasattr(tab, "_load_button")


def test_segmentation_tab_validation() -> None:
    """Validate single-channel layer checks.

    Returns
    -------
    None
    """
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    backend = _DummySegmentationBackend()
    tab = SegmentationTab(napari_viewer=viewer, backend=backend)
    assert backend.preloaded is True
    layer = DummyLayer(np.zeros((4, 4)), "img", rgb=False)
    assert tab._validate_single_channel_layer(layer, "Layer") is True
    rgb_layer = DummyLayer(np.zeros((4, 4, 3)), "rgb", rgb=True)
    assert tab._validate_single_channel_layer(rgb_layer, "Layer") is False


def test_segmentation_labels_include_task_metadata() -> None:
    """Tag generated segmentation labels with task metadata."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SegmentationTab(
        napari_viewer=viewer,
        backend=_DummySegmentationBackend(),
    )
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
    tab = SegmentationTab(
        napari_viewer=viewer,
        backend=_DummySegmentationBackend(),
    )
    source = DummyLayer(np.zeros((4, 4)), "img", metadata={"path": "file.tif"})

    tab._add_labels_layer(source, np.ones((4, 4), dtype=np.uint16), "model", "nuc")

    labels_layer = viewer.layers[-1]
    assert labels_layer.name == "img_model_nuc_labels_1"
    assert labels_layer.metadata.get("task") == "nuclear"
    assert labels_layer.metadata.get("path") == "file.tif"


def test_segmentation_labels_are_added_as_dask_arrays() -> None:
    """Wrap segmentation masks as dask arrays, then materialize layer data."""

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

    viewer = _CaptureViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SegmentationTab(
        napari_viewer=viewer,
        backend=_DummySegmentationBackend(),
    )
    source = DummyLayer(np.zeros((4, 4)), "img", metadata={"path": "file.tif"})

    tab._add_labels_layer(
        source,
        np.ones((4, 4), dtype=np.uint16),
        "model",
        "nuc",
    )

    assert isinstance(viewer.received, da.Array)
    assert isinstance(viewer.layers[-1].data, np.ndarray)


def test_segmentation_labels_preserve_source_run_history() -> None:
    """Keep source run history and append current model settings."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SegmentationTab(
        napari_viewer=viewer,
        backend=_DummySegmentationBackend(),
    )
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
    tab = SpotsTab(napari_viewer=viewer, backend=_DummySpotsBackend())
    assert hasattr(tab, "_detector_combo")


def test_segmentation_settings_state_round_trip() -> None:
    """Export and re-apply segmentation settings state."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SegmentationTab(
        napari_viewer=viewer,
        backend=_DummySegmentationBackend(),
    )

    tab.apply_settings_state(
        {
            "nuclear": {
                "model": "dummy_model",
                "settings": {"threshold": 0.7, "enabled": True},
            },
            "cytoplasmic": {
                "model": "dummy_model",
                "settings": {"threshold": 0.6, "enabled": True},
            },
        }
    )

    state = tab.export_settings_state()
    assert state["nuclear"]["model"] == "dummy_model"
    assert state["nuclear"]["settings"]["threshold"] == 0.7
    assert state["nuclear"]["settings"]["enabled"] is True
    assert state["cytoplasmic"]["settings"]["threshold"] == 0.6


def test_spots_settings_state_round_trip() -> None:
    """Export and re-apply spots detector settings state."""
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    tab = SpotsTab(
        napari_viewer=viewer,
        backend=_DummySpotsBackend(),
    )

    tab.apply_settings_state(
        {
            "detector": "dummy_detector",
            "settings": {"threshold": 0.55},
            "size_filter": {"min_size": 3, "max_size": 9},
        }
    )

    state = tab.export_settings_state()
    assert state["detector"] == "dummy_detector"
    assert state["settings"]["threshold"] == 0.55
    assert state["size_filter"]["min_size"] == 3
    assert state["size_filter"]["max_size"] == 9


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


def test_main_widget_instantiates(monkeypatch) -> None:
    """Instantiate the main SenoQuant widget.

    Returns
    -------
    None
    """
    monkeypatch.setattr(
        "senoquant.tabs.segmentation.backend.SegmentationBackend.preload_models",
        lambda self: None,
    )
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    widget = SenoQuantWidget(viewer)
    assert widget is not None
