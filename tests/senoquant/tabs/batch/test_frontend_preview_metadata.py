"""Tests for batch quantification preview label metadata."""

from __future__ import annotations

from senoquant.tabs.batch.config import BatchChannelConfig
from senoquant.tabs.batch.frontend import BatchTab
from senoquant.tabs.batch.layers import BatchViewer


class _Toggle:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _Combo:
    def __init__(self, text: str) -> None:
        self._text = text

    def currentText(self) -> str:
        return self._text


def test_refresh_config_viewer_adds_task_metadata_to_placeholder_labels() -> None:
    """Populate preview labels with task metadata for quantification."""
    tab = BatchTab.__new__(BatchTab)
    tab._channel_configs = [BatchChannelConfig(name="Ch0", index=0)]
    tab._config_viewer = BatchViewer()
    tab._nuclear_enabled = _Toggle(True)
    tab._nuclear_model_combo = _Combo("nuc_model")
    tab._nuclear_channel_combo = _Combo("Ch0")
    tab._cyto_enabled = _Toggle(True)
    tab._cyto_model_combo = _Combo("cyto_model")
    tab._cyto_channel_combo = _Combo("Ch0")
    tab._spots_enabled = _Toggle(True)
    tab._spot_detector_combo = _Combo("spotdet")
    tab._spot_channel_rows = [{"combo": _Combo("Ch0")}]

    tab._refresh_config_viewer()

    task_by_name = {
        layer.name: layer.metadata.get("task")
        for layer in tab._config_viewer.layers
        if layer.__class__.__name__ == "Labels"
    }
    assert task_by_name["Ch0_nuc_model_nuc_labels"] == "nuclear"
    assert task_by_name["Ch0_cyto_model_cyto_labels"] == "cytoplasmic"
    assert task_by_name["Ch0_spotdet_spot_labels"] == "spots"
