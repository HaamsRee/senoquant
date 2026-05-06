"""Tests for shared settings bundle helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from senoquant.utils import settings_bundle as settings_bundle_mod
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


def test_parse_settings_bundle_non_dict_returns_default_bundle() -> None:
    """Ignore non-dict payloads and return default bundle shape."""
    payload = parse_settings_bundle("legacy-profile")
    assert payload["batch_job"] == {}
    assert payload["tab_settings"] == {}
    assert payload["feature_settings"] == {}
    assert payload["segmentation_runs"] == []


def test_build_settings_bundle_json_safe_path_and_item_values() -> None:
    """Convert Path and scalar-like ``item()`` values to JSON-safe payloads."""

    class _ScalarLike:
        def __init__(self, value) -> None:
            self._value = value

        def item(self):
            return self._value

    payload = build_settings_bundle(
        batch_job={
            "input_path": Path("/tmp/input"),
            "windows_style_path": Path("C:/tmp/input"),
            "threshold": _ScalarLike(0.75),
            Path("/tmp/key"): "path-key",
        }
    )

    assert payload["batch_job"]["input_path"] == "/tmp/input"
    assert payload["batch_job"]["windows_style_path"] == "C:/tmp/input"
    assert payload["batch_job"]["/tmp/key"] == "path-key"
    assert payload["batch_job"]["threshold"] == pytest.approx(0.75)


def test_build_settings_bundle_json_safe_item_failure_uses_string() -> None:
    """Fallback to string conversion when scalar-like ``item()`` fails."""

    class _BrokenScalar:
        def item(self):
            raise RuntimeError("broken")

        def __str__(self) -> str:
            return "broken-scalar"

    payload = build_settings_bundle(batch_job={"value": _BrokenScalar()})
    assert payload["batch_job"]["value"] == "broken-scalar"


def test_load_settings_bundle_json_schema_rejects_non_dict_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Raise ValueError when schema JSON payload is not an object."""
    bad_schema = tmp_path / "settings_bundle.schema.json"
    bad_schema.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        settings_bundle_mod,
        "SETTINGS_BUNDLE_JSON_SCHEMA_PATH",
        bad_schema,
    )

    with pytest.raises(ValueError, match="Invalid settings bundle schema payload"):
        load_settings_bundle_json_schema()
