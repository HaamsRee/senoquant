"""Smoke tests for Qt-based frontends.

Notes
-----
These tests instantiate frontend widgets with stubbed Qt classes to
validate basic wiring and helper behaviors.
"""

from __future__ import annotations

import dask.array as da
import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget

from tests.conftest import DummyLayer, DummyViewer
from senoquant._widget import SenoQuantWidget
from senoquant.tabs.batch.frontend import BatchTab
from senoquant.tabs.quantification.frontend import QuantificationTab
from senoquant.tabs.sennet_portal.backend import SenNetDataset
from senoquant.tabs.sennet_portal.frontend import SenNetPortalTab
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


class _DummySenNetPortalBackend:
    """Minimal SenNet backend stub for portal UI smoke tests."""

    ANTIBODY_DATASET_TYPES = ("PhenoCycler", "CODEX")

    def globus_login_status(self) -> tuple[bool, str]:
        return False, "Not logged in"

    def gcp_installation_status(self) -> tuple[bool, str]:
        return True, "endpoint-1"

    def available_antibody_dataset_types(self, *, token=None, max_types: int = 200) -> list[str]:
        return ["CODEX", "PhenoCycler"]

    def search_datasets(self, **_kwargs) -> list[SenNetDataset]:
        return []

    def download_datasets(self, _datasets, _destination) -> dict[str, object]:
        return {"dataset_count": 0, "file_count": 0, "destination": "", "task_ids": []}

    def download_tasks_status(self, _task_ids) -> dict[str, object]:
        return {
            "task_count": 0,
            "overall_status": "SUCCEEDED",
            "all_complete": True,
            "all_succeeded": True,
            "any_failed": False,
            "progress_percent": 100,
            "files": 0,
            "files_transferred": 0,
            "subtasks_total": 0,
            "subtasks_completed": 0,
            "speed_bps": 0,
            "bytes_transferred": 0,
            "tasks": [],
        }

    def cancel_download_tasks(self, _task_ids) -> None:
        return None

    def login_globus(self) -> None:
        return None

    def logout_globus(self) -> None:
        return None


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


def test_sennet_portal_tab_instantiates() -> None:
    """Instantiate the SenNet portal tab UI."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    assert hasattr(tab, "_dataset_table")
    assert hasattr(tab, "_download_button")
    assert hasattr(tab, "_cancel_download_button")
    assert hasattr(tab, "_select_all_button")
    assert hasattr(tab, "_clear_all_button")
    assert hasattr(tab, "_gcp_status_label")
    assert hasattr(tab, "_gcp_install_button")
    assert hasattr(tab, "_gcp_check_again_button")
    assert hasattr(tab, "_clear_filters_button")
    assert tab._dataset_table.cellWidget(0, 1) is not None
    assert tab._cancel_download_button.isEnabled() is False


def test_sennet_portal_select_all_and_clear_all() -> None:
    """Apply Select/Clear actions only to visible rows."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            ),
            SenNetDataset(
                sennet_id="SNT2",
                dataset_type="CODEX",
                status="Published",
                access_level="public",
                title="Dataset 2",
                compatible_paths=["/raw/b.ome.tif"],
                compatible_extensions=[".ome.tif"],
                source_type="Mouse",
                organ="Lung",
            ),
        ]
    )

    assert 0 not in tab._column_filter_combos
    tab._column_filter_combos[3].setCurrentText("Human")
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is True
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked

    tab._clear_all_datasets()
    assert tab._column_filter_combos[3].currentText() == "Human"
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is True
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Unchecked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked

    tab._select_all_datasets()
    assert tab._column_filter_combos[3].currentText() == "Human"
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is True
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked

    tab._clear_filters()
    assert tab._column_filter_combos[3].currentText() == "All"
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is False
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked


def test_sennet_portal_column_filter_hides_nonmatching_rows() -> None:
    """Apply source/organ filters and hide plus uncheck excluded rows."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            ),
            SenNetDataset(
                sennet_id="SNT2",
                dataset_type="CODEX",
                status="Published",
                access_level="public",
                title="Dataset 2",
                compatible_paths=["/raw/b.ome.tif"],
                compatible_extensions=[".ome.tif"],
                source_type="Mouse",
                organ="Pancreas",
            ),
        ]
    )

    tab._column_filter_combos[3].setCurrentText("Human")
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is True
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked

    tab._column_filter_combos[3].setCurrentText("All")
    tab._column_filter_combos[4].setCurrentText("Pancreas")
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is False
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Checked


def test_sennet_portal_age_range_filter_hides_rows_outside_bounds() -> None:
    """Apply age min/max range filter using the Age header row widget."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
                sample_age="30 years",
                sample_age_value=30.0,
                sample_age_unit="years",
            ),
            SenNetDataset(
                sennet_id="SNT2",
                dataset_type="CODEX",
                status="Published",
                access_level="public",
                title="Dataset 2",
                compatible_paths=["/raw/b.ome.tif"],
                compatible_extensions=[".ome.tif"],
                source_type="Human",
                organ="Pancreas",
                sample_age="70 years",
                sample_age_value=70.0,
                sample_age_unit="years",
            ),
        ]
    )

    tab._age_filter_min_input.setText("40")
    tab._age_filter_max_input.setText("80")
    assert tab._dataset_table.isRowHidden(1) is True
    assert tab._dataset_table.isRowHidden(2) is False
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Unchecked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Checked

    tab._clear_filters()
    assert tab._age_filter_min_input.text() == ""
    assert tab._age_filter_max_input.text() == ""
    assert tab._dataset_table.isRowHidden(1) is False
    assert tab._dataset_table.isRowHidden(2) is False


def test_sennet_portal_download_button_locked_until_task_completion() -> None:
    """Disable download button while active transfer tasks are still running."""

    class _ActiveTaskBackend(_DummySenNetPortalBackend):
        def download_tasks_status(self, _task_ids) -> dict[str, object]:
            return {
                "task_count": 1,
                "overall_status": "ACTIVE",
                "all_complete": False,
                "all_succeeded": False,
                "any_failed": False,
                "progress_percent": 25,
                "files": 4,
                "files_transferred": 1,
                "subtasks_total": 8,
                "subtasks_completed": 2,
                "speed_bps": 1024,
                "bytes_transferred": 2048,
                "tasks": [],
            }

    tab = SenNetPortalTab(backend=_ActiveTaskBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            )
        ]
    )

    tab._on_download_complete(
        {
            "dataset_count": 1,
            "file_count": 4,
            "destination": "/tmp/downloads",
            "task_ids": ["5724a523-11aa-11f1-a049-0e5b09a3151b"],
        }
    )
    assert tab._download_button.isEnabled() is False
    assert tab._cancel_download_button.isEnabled() is True
    assert tab._download_progress_bar._visible is True
    assert "Transfer" in tab._download_speed_label.text()

    tab._on_download_progress(
        {
            "task_count": 1,
            "overall_status": "SUCCEEDED",
            "all_complete": True,
            "all_succeeded": True,
            "any_failed": False,
            "progress_percent": 100,
            "files": 4,
            "files_transferred": 4,
            "subtasks_total": 8,
            "subtasks_completed": 8,
            "speed_bps": 0,
            "bytes_transferred": 1234,
            "tasks": [],
        }
    )
    assert tab._download_button.isEnabled() is True
    assert tab._cancel_download_button.isEnabled() is False


def test_sennet_portal_progress_poll_error_keeps_pending_task_ids() -> None:
    """Keep active task IDs after transient polling failures and allow retry."""

    class _FlakyTaskBackend(_DummySenNetPortalBackend):
        def __init__(self) -> None:
            self.poll_calls = 0

        def download_tasks_status(self, _task_ids) -> dict[str, object]:
            self.poll_calls += 1
            if self.poll_calls == 1:
                raise RuntimeError("temporary monitoring error")
            return {
                "task_count": 1,
                "overall_status": "SUCCEEDED",
                "all_complete": True,
                "all_succeeded": True,
                "any_failed": False,
                "progress_percent": 100,
                "files": 4,
                "files_transferred": 4,
                "subtasks_total": 8,
                "subtasks_completed": 8,
                "speed_bps": 0,
                "bytes_transferred": 1234,
                "tasks": [],
            }

    tab = SenNetPortalTab(backend=_FlakyTaskBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            )
        ]
    )

    task_id = "5724a523-11aa-11f1-a049-0e5b09a3151b"
    tab._on_download_complete(
        {
            "dataset_count": 1,
            "file_count": 4,
            "destination": "/tmp/downloads",
            "task_ids": [task_id],
        }
    )

    assert tab._download_locked is True
    assert tab._download_task_ids == [task_id]
    assert tab._cancel_download_button.isEnabled() is True
    assert "retry automatically" in tab._status_label.text().lower()

    # QTimer is stubbed in tests, so manually trigger one retry poll.
    tab._poll_download_tasks()
    assert tab._download_locked is False
    assert tab._download_task_ids == []
    assert tab._cancel_download_button.isEnabled() is False


def test_sennet_portal_progress_label_prefers_file_counts() -> None:
    """Show file counters in the transfer status label when available."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    tab._download_locked = True
    tab._on_download_progress(
        {
            "task_count": 1,
            "overall_status": "ACTIVE",
            "all_complete": False,
            "all_succeeded": False,
            "any_failed": False,
            "progress_percent": 40,
            "files": 10,
            "files_transferred": 4,
            "subtasks_total": 80,
            "subtasks_completed": 20,
            "speed_bps": 1024,
            "bytes_transferred": 4096,
            "tasks": [],
        }
    )
    assert "(4/10 files)" in tab._download_speed_label.text()


def test_sennet_portal_cancel_download_resets_ui_status() -> None:
    """Cancel active transfer and reset visible transfer status widgets."""
    class _ActiveTaskBackend(_DummySenNetPortalBackend):
        def download_tasks_status(self, _task_ids) -> dict[str, object]:
            return {
                "task_count": 1,
                "overall_status": "ACTIVE",
                "all_complete": False,
                "all_succeeded": False,
                "any_failed": False,
                "progress_percent": 25,
                "files": 4,
                "files_transferred": 1,
                "subtasks_total": 8,
                "subtasks_completed": 2,
                "speed_bps": 1024,
                "bytes_transferred": 2048,
                "tasks": [],
            }

    tab = SenNetPortalTab(backend=_ActiveTaskBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            )
        ]
    )

    tab._on_download_complete(
        {
            "dataset_count": 1,
            "file_count": 4,
            "destination": "/tmp/downloads",
            "task_ids": ["5724a523-11aa-11f1-a049-0e5b09a3151b"],
        }
    )
    tab.cancel_active_downloads()

    assert tab._download_button.isEnabled() is True
    assert tab._cancel_download_button.isEnabled() is False
    assert tab._download_progress_bar._visible is False
    assert tab._download_speed_label._visible is False
    assert tab._download_progress_bar._value == 0
    assert tab._download_speed_label.text() == ""
    assert tab._status_label.text() == "Download canceled."


def test_sennet_portal_header_sort_preserves_check_states() -> None:
    """Sort table by heading and preserve include checkboxes per dataset."""
    tab = SenNetPortalTab(backend=_DummySenNetPortalBackend())
    tab._on_search_complete(
        [
            SenNetDataset(
                sennet_id="SNT2",
                dataset_type="CODEX",
                status="Published",
                access_level="public",
                title="Dataset 2",
                compatible_paths=["/raw/b.ome.tif"],
                compatible_extensions=[".ome.tif"],
                source_type="Mouse",
                organ="Pancreas",
            ),
            SenNetDataset(
                sennet_id="SNT1",
                dataset_type="PhenoCycler",
                status="Published",
                access_level="public",
                title="Dataset 1",
                compatible_paths=["/raw/a.qptiff"],
                compatible_extensions=[".qptiff"],
                source_type="Human",
                organ="Pancreas",
            ),
        ]
    )

    tab._dataset_table.item(1, 0).setCheckState(Qt.Unchecked)
    tab._on_table_header_clicked(1)
    assert tab._dataset_table.item(1, 1).text() == "SNT1"
    assert tab._dataset_table.item(2, 1).text() == "SNT2"
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Checked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Unchecked

    tab._on_table_header_clicked(1)
    assert tab._dataset_table.item(1, 1).text() == "SNT2"
    assert tab._dataset_table.item(2, 1).text() == "SNT1"
    assert tab._dataset_table.item(1, 0).checkState() == Qt.Unchecked
    assert tab._dataset_table.item(2, 0).checkState() == Qt.Checked


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
    monkeypatch.setattr(
        "senoquant._widget.SenNetPortalTab",
        lambda napari_viewer=None: SenNetPortalTab(
            backend=_DummySenNetPortalBackend(),
            napari_viewer=napari_viewer,
        ),
    )
    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    widget = SenoQuantWidget(viewer)
    assert widget is not None


def test_main_widget_puts_sennet_portal_first(monkeypatch) -> None:
    """Add SenNet Portal before segmentation in the main tab order."""
    monkeypatch.setattr(
        "senoquant.tabs.segmentation.backend.SegmentationBackend.preload_models",
        lambda self: None,
    )
    monkeypatch.setattr(
        "senoquant._widget.SenNetPortalTab",
        lambda napari_viewer=None: SenNetPortalTab(
            backend=_DummySenNetPortalBackend(),
            napari_viewer=napari_viewer,
        ),
    )

    captured: dict[str, list[str]] = {"labels": []}

    class _RecordingTabWidget:
        def __init__(self, *_args, **_kwargs) -> None:
            captured["labels"] = []

        def addTab(self, _widget, label: str) -> None:
            captured["labels"].append(label)

    monkeypatch.setattr("senoquant._widget.QTabWidget", _RecordingTabWidget)

    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    SenoQuantWidget(viewer)
    assert captured["labels"][0] == "SenNet Portal"
    assert captured["labels"][1] == "Segmentation"


def test_main_widget_runs_shutdown_on_qt_application_quit(monkeypatch) -> None:
    """Run global shutdown hooks from QApplication close/quit signals once."""

    class _TrackingTab(QWidget):
        def __init__(self, *_args, **_kwargs) -> None:
            super().__init__()
            self.shutdown_calls = 0

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    monkeypatch.setattr("senoquant._widget.SegmentationTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.SpotsTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.PredictionTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.QuantificationTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.VisualizationTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.BatchTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.SettingsTab", _TrackingTab)
    monkeypatch.setattr("senoquant._widget.SenNetPortalTab", _TrackingTab)

    class _Signal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self) -> None:
            for callback in list(self._callbacks):
                callback()

    class _QApplication:
        _instance = None

        @classmethod
        def instance(cls):
            return cls._instance

    _QApplication._instance = type(
        "_App",
        (),
        {"lastWindowClosed": _Signal(), "aboutToQuit": _Signal()},
    )()
    monkeypatch.setattr("senoquant._widget.QtWidgets.QApplication", _QApplication, raising=False)

    viewer = DummyViewer([DummyLayer(np.zeros((4, 4)), "img")])
    widget = SenoQuantWidget(viewer)
    portal = widget._sennet_portal_tab
    assert isinstance(portal, _TrackingTab)

    _QApplication._instance.lastWindowClosed.emit()
    assert portal.shutdown_calls == 1

    # Widget close is a second shutdown path; hooks should still run once.
    widget.closeEvent(object())
    assert portal.shutdown_calls == 1
