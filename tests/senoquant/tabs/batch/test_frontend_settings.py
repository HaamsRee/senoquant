"""Tests for batch frontend settings import/export helpers."""

from __future__ import annotations

from tests.conftest import DummyLayer, DummyViewer
from senoquant.tabs.batch.config import BatchJobConfig
from senoquant.tabs.batch.frontend import BatchTab


def test_batch_frontend_exposes_programmatic_job_config_api() -> None:
    """Expose public export/apply APIs for settings-tab integration."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)

    assert not hasattr(tab, "_save_profile")
    assert not hasattr(tab, "_load_profile")

    job = tab.export_job_config()
    assert isinstance(job, BatchJobConfig)


def test_batch_frontend_apply_job_config_populates_ui() -> None:
    """Apply batch job config through public wrapper."""
    viewer = DummyViewer([DummyLayer(None, "img")])
    tab = BatchTab(napari_viewer=viewer)
    tab._quant_tab.load_feature_configs = lambda _features: None
    job = BatchJobConfig(
        input_path="/input",
        output_path="/output",
        extensions=[".tif", ".czi"],
        include_subfolders=True,
        process_all_scenes=True,
    )

    tab.apply_job_config(job)

    assert tab._input_path.text() == "/input"
    assert tab._output_path.text() == "/output"
    assert tab._extensions.text() == ".tif,.czi"
    assert tab._include_subfolders.isChecked() is True
    assert tab._process_scenes.isChecked() is True
