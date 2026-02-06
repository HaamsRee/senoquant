"""Tests for shared settings bundle helpers."""

from __future__ import annotations

from senoquant.settings_bundle import build_settings_bundle, parse_settings_bundle


def test_build_settings_bundle_defaults() -> None:
    """Build default bundle shape with schema metadata."""
    payload = build_settings_bundle()
    assert payload["schema"] == "senoquant.settings"
    assert payload["version"] == 1
    assert payload["batch_job"] == {}
    assert payload["feature"] == {}
    assert payload["segmentation_runs"] == []


def test_parse_settings_bundle_wraps_legacy_batch_payload() -> None:
    """Treat legacy profiles as batch payloads in the new envelope."""
    legacy = {"input_path": "/input", "output_path": "/output"}
    payload = parse_settings_bundle(legacy)
    assert payload["schema"] == "senoquant.settings"
    assert payload["batch_job"]["input_path"] == "/input"
