"""Tests for shared settings bundle helpers."""

from __future__ import annotations

from senoquant.utils.settings_bundle import (
    build_settings_bundle,
    load_settings_bundle_json_schema,
    parse_settings_bundle,
)


def test_build_settings_bundle_defaults() -> None:
    """Build default bundle shape with schema metadata."""
    payload = build_settings_bundle()
    assert payload["schema"] == "senoquant.settings"
    assert payload["version"] == 1
    assert payload["batch_job"] == {}
    assert payload["tab_settings"] == {}
    assert payload["feature_settings"] == {}
    assert payload["segmentation_runs"] == []


def test_parse_settings_bundle_wraps_legacy_batch_payload() -> None:
    """Treat legacy profiles as batch payloads in the new envelope."""
    legacy = {"input_path": "/input", "output_path": "/output"}
    payload = parse_settings_bundle(legacy)
    assert payload["schema"] == "senoquant.settings"
    assert payload["batch_job"]["input_path"] == "/input"


def test_parse_settings_bundle_maps_legacy_feature_tab_settings() -> None:
    """Map legacy ``feature`` tab-settings payloads into ``tab_settings``."""
    legacy_bundle = {
        "schema": "senoquant.settings",
        "version": 1,
        "feature": {
            "kind": "tab_settings",
            "segmentation": {"nuclear": {"model": "default_2d"}},
            "spots": {"detector": "ufish"},
        },
    }
    payload = parse_settings_bundle(legacy_bundle)
    assert payload["tab_settings"]["kind"] == "tab_settings"
    assert payload["tab_settings"]["segmentation"]["nuclear"]["model"] == "default_2d"
    assert payload["feature_settings"] == {}


def test_parse_settings_bundle_maps_legacy_feature_feature_settings() -> None:
    """Map legacy quantification ``feature`` payloads into ``feature_settings``."""
    legacy_bundle = {
        "schema": "senoquant.settings",
        "version": 1,
        "feature": {
            "feature_type": "Markers",
            "feature_name": "Markers",
        },
    }
    payload = parse_settings_bundle(legacy_bundle)
    assert payload["feature_settings"]["feature_type"] == "Markers"
    assert payload["tab_settings"] == {}


def test_settings_bundle_json_schema_matches_bundle_defaults() -> None:
    """Ensure schema constants and required keys match payload defaults."""
    schema = load_settings_bundle_json_schema()
    payload = build_settings_bundle()

    assert schema["properties"]["schema"]["const"] == payload["schema"]
    assert schema["properties"]["version"]["const"] == payload["version"]

    required_keys = set(schema["required"])
    assert required_keys.issubset(payload.keys())
