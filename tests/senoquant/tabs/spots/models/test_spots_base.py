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
    detector.details_path.write_text(json.dumps({"settings": [{"name": "ld"}]}))
    assert detector.list_settings()[0]["name"] == "ld"
