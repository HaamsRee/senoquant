"""Tests for setting tooltip generation."""

from __future__ import annotations

from senoquant.utils.setting_tooltips import build_setting_tooltip


def test_build_setting_tooltip_uses_explicit_text() -> None:
    """Include explicit tooltip plus normalized metadata lines."""
    setting = {
        "key": "threshold",
        "type": "float",
        "tooltip": "Probability cutoff for detections.",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
    }

    tooltip = build_setting_tooltip(setting)

    assert "Probability cutoff for detections." in tooltip
    assert "Type: float" in tooltip
    assert "Default: 0.5" in tooltip
    assert "Range: 0 to 1" in tooltip


def test_build_setting_tooltip_formats_bool_and_dependencies() -> None:
    """Format boolean defaults and dependency metadata."""
    setting = {
        "key": "auto_threshold",
        "type": "bool",
        "default": True,
        "enabled_by": "advanced_mode",
    }

    tooltip = build_setting_tooltip(setting)

    assert "Type: bool" in tooltip
    assert "Default: enabled" in tooltip
    assert "Enabled when 'advanced_mode' is enabled." in tooltip


def test_build_setting_tooltip_uses_description_fallback_and_disabled_by() -> None:
    """Use description text when tooltip is absent and include disabled dependency."""
    setting = {
        "key": "manual_threshold",
        "description": "Manual threshold used when auto mode is disabled.",
        "type": "float",
        "default": 0.25,
        "min": 0.0,
        "max": 1.0,
        "disabled_by": "auto_threshold",
    }

    tooltip = build_setting_tooltip(setting)

    assert "Manual threshold used when auto mode is disabled." in tooltip
    assert "Disabled when 'auto_threshold' is enabled." in tooltip


def test_build_setting_tooltip_returns_empty_for_missing_metadata() -> None:
    """Return empty tooltip text when no fields are available."""
    assert build_setting_tooltip({}) == ""
