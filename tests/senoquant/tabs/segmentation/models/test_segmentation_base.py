"""Tests for segmentation model base class.

Notes
-----
Validates detail parsing and task metadata helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from senoquant.tabs.segmentation.models.base import SenoQuantSegmentationModel


def test_model_name_validation(tmp_path: Path) -> None:
    """Reject empty model names.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        SenoQuantSegmentationModel("", models_root=tmp_path)


def test_model_details_helpers(tmp_path: Path) -> None:
    """Read settings and task metadata from details.json.

    Returns
    -------
    None
    """
    model = SenoQuantSegmentationModel("demo", models_root=tmp_path)
    details = {
        "settings": [{"name": "threshold", "type": "float"}],
        "tasks": {
            "nuclear": {"supported": True},
            "cytoplasmic": {
                "supported": True,
                "input_modes": ["nuclear+cytoplasmic"],
                "nuclear_channel_optional": False,
            },
        },
    }
    model.details_path.write_text(json.dumps(details))

    assert model.list_settings()[0]["name"] == "threshold"
    assert model.supports_task("nuclear") is True
    assert model.cytoplasmic_input_modes() == ["nuclear+cytoplasmic"]
    assert model.cytoplasmic_nuclear_optional() is False
