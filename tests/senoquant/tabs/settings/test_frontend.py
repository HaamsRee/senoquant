"""Tests for Settings tab save/load behavior."""

from __future__ import annotations

import json

from senoquant.tabs.batch.config import BatchJobConfig
from senoquant.tabs.settings.backend import SettingsBackend
from senoquant.tabs.settings.frontend import SettingsTab


class _SegmentationTabStub:
    """Segmentation tab stub for settings save/load tests."""

    def __init__(self) -> None:
        self.applied: dict | None = None

    def export_settings_state(self) -> dict:
        return {"nuclear": {"model": "default_2d", "settings": {"threshold": 0.2}}}

    def apply_settings_state(self, payload: dict) -> None:
        self.applied = dict(payload)


class _SpotsTabStub:
    """Spots tab stub for settings save/load tests."""

    def __init__(self) -> None:
        self.applied: dict | None = None

    def export_settings_state(self) -> dict:
        return {
            "detector": "ufish",
            "settings": {"threshold": 0.5},
            "size_filter": {"min_size": 2, "max_size": 10},
        }

    def apply_settings_state(self, payload: dict) -> None:
        self.applied = dict(payload)


class _BatchTabStub:
    """Batch tab stub for settings save/load tests."""

    def __init__(self) -> None:
        self.applied: BatchJobConfig | None = None

    def export_job_config(self) -> BatchJobConfig:
        return BatchJobConfig(input_path="/input", output_path="/output")

    def apply_job_config(self, job: BatchJobConfig) -> None:
        self.applied = job


def test_settings_tab_save_writes_unified_bundle(tmp_path, monkeypatch) -> None:
    """Save settings as a unified bundle with optional batch payload."""
    seg_tab = _SegmentationTabStub()
    spots_tab = _SpotsTabStub()
    batch_tab = _BatchTabStub()
    tab = SettingsTab(
        backend=SettingsBackend(),
        segmentation_tab=seg_tab,
        spots_tab=spots_tab,
        batch_tab=batch_tab,
    )

    output_path = tmp_path / "senoquant_settings.json"
    monkeypatch.setattr(
        "senoquant.tabs.settings.frontend.QFileDialog.getSaveFileName",
        lambda *_args, **_kwargs: (str(output_path), "JSON (*.json)"),
    )

    tab._save_settings()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "senoquant.settings"
    assert payload["feature"]["segmentation"]["nuclear"]["model"] == "default_2d"
    assert payload["feature"]["spots"]["detector"] == "ufish"
    assert payload["batch_job"]["input_path"] == "/input"


def test_settings_tab_load_applies_seg_spots_and_batch(tmp_path, monkeypatch) -> None:
    """Load settings and populate segmentation, spots, and batch tabs."""
    seg_tab = _SegmentationTabStub()
    spots_tab = _SpotsTabStub()
    batch_tab = _BatchTabStub()
    tab = SettingsTab(
        backend=SettingsBackend(),
        segmentation_tab=seg_tab,
        spots_tab=spots_tab,
        batch_tab=batch_tab,
    )

    payload = SettingsBackend().build_bundle(
        segmentation={"nuclear": {"model": "default_2d", "settings": {"a": 1}}},
        spots={"detector": "ufish", "settings": {"b": 2}},
        batch_job={"input_path": "/from-json", "output_path": "/out-json"},
    )
    input_path = tmp_path / "settings.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        "senoquant.tabs.settings.frontend.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(input_path), "JSON (*.json)"),
    )

    tab._load_settings()

    assert seg_tab.applied == {"nuclear": {"model": "default_2d", "settings": {"a": 1}}}
    assert spots_tab.applied == {"detector": "ufish", "settings": {"b": 2}}
    assert isinstance(batch_tab.applied, BatchJobConfig)
    assert batch_tab.applied.input_path == "/from-json"
    assert batch_tab.applied.output_path == "/out-json"
