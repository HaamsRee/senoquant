"""Tests for settings persistence backend."""

from __future__ import annotations

from senoquant.tabs.settings.backend import SettingsBackend


def test_settings_backend_build_bundle() -> None:
    """Build a canonical bundle containing tab and batch payloads."""
    backend = SettingsBackend()
    payload = backend.build_bundle(
        segmentation={"nuclear": {"model": "default_2d"}},
        spots={"detector": "ufish"},
        batch_job={"input_path": "/input"},
    )

    assert payload["schema"] == "senoquant.settings"
    assert payload["version"] == 1
    assert payload["feature"]["kind"] == "tab_settings"
    assert payload["feature"]["segmentation"]["nuclear"]["model"] == "default_2d"
    assert payload["feature"]["spots"]["detector"] == "ufish"
    assert payload["batch_job"]["input_path"] == "/input"


def test_settings_backend_save_and_load_bundle(tmp_path) -> None:
    """Round-trip settings bundle payloads through JSON files."""
    backend = SettingsBackend()
    source = backend.build_bundle(
        segmentation={"cytoplasmic": {"model": "nuclear_dilation"}},
        spots={"detector": "ufish"},
    )
    output_path = tmp_path / "senoquant_settings.json"
    backend.save_bundle(output_path, source)

    loaded = backend.load_bundle(output_path)
    assert loaded["schema"] == "senoquant.settings"
    assert loaded["feature"]["segmentation"]["cytoplasmic"]["model"] == "nuclear_dilation"
    assert loaded["feature"]["spots"]["detector"] == "ufish"
