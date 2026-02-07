"""Tests for model-details JSON Schema helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from senoquant.utils.model_details_schema import (
    load_model_details_json_schema,
    validate_model_details,
)


def _valid_spot_payload() -> dict:
    return {
        "name": "demo",
        "description": "Demo detector",
        "version": "0.1.0",
        "settings": [
            {
                "key": "auto_threshold",
                "label": "Auto threshold",
                "type": "bool",
                "default": True,
            }
        ],
    }


def _valid_segmentation_payload() -> dict:
    payload = _valid_spot_payload()
    payload["tasks"] = {
        "nuclear": {"supported": True},
        "cytoplasmic": {
            "supported": False,
        },
    }
    return payload


def test_load_model_details_json_schema() -> None:
    """Load schema and verify required top-level keys."""
    schema = load_model_details_json_schema()
    required = set(schema.get("required", []))
    assert {"name", "description", "version", "settings"} <= required


def test_validate_model_details_spots_payload() -> None:
    """Validate a spots-style details payload."""
    payload = validate_model_details(
        _valid_spot_payload(),
        details_path=Path("details.json"),
        require_tasks=False,
    )
    assert payload["name"] == "demo"


def test_validate_model_details_requires_tasks_for_segmentation() -> None:
    """Reject segmentation payloads that omit tasks metadata."""
    with pytest.raises(ValueError, match="must define 'tasks'"):
        validate_model_details(
            _valid_spot_payload(),
            details_path=Path("details.json"),
            require_tasks=True,
        )


def test_validate_model_details_segmentation_payload() -> None:
    """Validate a segmentation-style details payload."""
    payload = validate_model_details(
        _valid_segmentation_payload(),
        details_path=Path("details.json"),
        require_tasks=True,
    )
    assert "tasks" in payload


def test_validate_model_details_rejects_non_object_payload() -> None:
    """Reject non-dictionary payload values."""
    with pytest.raises(ValueError, match="expected JSON object"):
        validate_model_details(
            ["not", "an", "object"],
            details_path=Path("details.json"),
            require_tasks=False,
        )


def test_validate_model_details_requires_both_segmentation_tasks() -> None:
    """Require both nuclear and cytoplasmic task entries."""
    payload = _valid_segmentation_payload()
    payload["tasks"].pop("cytoplasmic")

    with pytest.raises(ValueError, match="missing tasks.cytoplasmic"):
        validate_model_details(
            payload,
            details_path=Path("details.json"),
            require_tasks=True,
        )


def test_validate_model_details_rejects_invalid_setting_payload() -> None:
    """Reject invalid setting entries with schema errors."""
    payload = _valid_spot_payload()
    payload["settings"] = [{"label": "missing key", "type": "bool", "default": True}]

    with pytest.raises(ValueError, match="Invalid model details"):
        validate_model_details(
            payload,
            details_path=Path("details.json"),
            require_tasks=False,
        )
