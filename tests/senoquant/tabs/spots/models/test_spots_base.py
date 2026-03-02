"""Tests for spot detector base class.

Notes
-----
Validates basic metadata helpers and validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from senoquant.tabs.spots.models.base import SenoQuantSpotDetector


def test_detector_name_validation(tmp_path: Path) -> None:
    """Reject empty detector names.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        SenoQuantSpotDetector("", models_root=tmp_path)


def test_detector_details_helpers(tmp_path: Path) -> None:
    """Load detector settings from details.json.

    Returns
    -------
    None
    """
    detector = SenoQuantSpotDetector("demo", models_root=tmp_path)
    detector.details_path.write_text(
        json.dumps(
            {
                "name": "demo",
                "description": "Demo detector",
                "version": "0.1.0",
                "settings": [
                    {
                        "key": "ld",
                        "label": "LD",
                        "type": "bool",
                        "default": False,
                    }
                ],
            }
        )
    )
    assert detector.list_settings()[0]["key"] == "ld"


def test_detector_details_validation(tmp_path: Path) -> None:
    """Reject invalid detector settings schema payloads."""
    detector = SenoQuantSpotDetector("demo", models_root=tmp_path)
    detector.details_path.write_text(
        json.dumps(
            {
                "name": "demo",
                "description": "Demo detector",
                "version": "0.1.0",
                "settings": [{"label": "Missing key", "type": "bool", "default": True}],
            }
        )
    )

    with pytest.raises(ValueError, match="Invalid model details"):
        detector.load_details()


def test_detector_paths_and_missing_details_defaults(tmp_path: Path) -> None:
    """Expose path helpers and safe defaults when details file is absent."""
    detector = SenoQuantSpotDetector("demo", models_root=tmp_path)

    assert detector.details_path == tmp_path / "demo" / "details.json"
    assert detector.class_path == tmp_path / "demo" / "model.py"
    assert detector.load_details() == {}
    assert detector.list_settings() == []
    assert detector.display_order() is None


def test_detector_list_settings_handles_non_list(monkeypatch, tmp_path: Path) -> None:
    """Return empty list when details payload contains non-list settings."""
    detector = SenoQuantSpotDetector("demo", models_root=tmp_path)
    monkeypatch.setattr(detector, "load_details", lambda: {"settings": {"bad": True}})
    assert detector.list_settings() == []


def test_detector_display_order_parsing_and_run_base(monkeypatch, tmp_path: Path) -> None:
    """Parse order variants and keep base run method abstract."""
    detector = SenoQuantSpotDetector("demo", models_root=tmp_path)

    monkeypatch.setattr(detector, "load_details", lambda: {"order": 2})
    assert detector.display_order() == 2.0

    monkeypatch.setattr(detector, "load_details", lambda: {"order": "3.5"})
    assert detector.display_order() == 3.5

    monkeypatch.setattr(detector, "load_details", lambda: {"order": "not-a-number"})
    assert detector.display_order() is None

    with pytest.raises(NotImplementedError):
        detector.run()
