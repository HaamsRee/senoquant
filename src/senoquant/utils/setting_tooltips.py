"""Helpers for building user-facing setting tooltips."""

from __future__ import annotations

from typing import Mapping


def _as_text(value: object) -> str:
    """Return a trimmed string value or an empty string."""
    if isinstance(value, str):
        return value.strip()
    return ""


def _format_value(value: object) -> str:
    """Format a setting value for tooltip text."""
    if isinstance(value, bool):
        return "enabled" if value else "disabled"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def build_setting_tooltip(setting: Mapping[str, object]) -> str:
    """Build tooltip text from a setting metadata mapping.

    Parameters
    ----------
    setting : Mapping[str, object]
        Setting entry loaded from a model ``details.json``.

    Returns
    -------
    str
        Tooltip text. Empty string when no tooltip can be built.
    """
    parts: list[str] = []

    for field in ("tooltip", "description", "help"):
        text = _as_text(setting.get(field))
        if text:
            parts.append(text)
            break

    setting_type = _as_text(setting.get("type"))
    if setting_type:
        parts.append(f"Type: {setting_type}")

    if "default" in setting:
        parts.append(f"Default: {_format_value(setting.get('default'))}")

    if "min" in setting and "max" in setting:
        min_value = _format_value(setting.get("min"))
        max_value = _format_value(setting.get("max"))
        parts.append(f"Range: {min_value} to {max_value}")

    enabled_by = _as_text(setting.get("enabled_by"))
    if enabled_by:
        parts.append(f"Enabled when '{enabled_by}' is enabled.")

    disabled_by = _as_text(setting.get("disabled_by"))
    if disabled_by:
        parts.append(f"Disabled when '{disabled_by}' is enabled.")

    return "\n".join(parts).strip()
