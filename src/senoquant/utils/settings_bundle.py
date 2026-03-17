"""Shared settings bundle serialization helpers.

This module defines the ``senoquant.settings`` envelope used across:
- Batch settings persistence.
- Quantification feature export settings payloads.

The envelope keeps payload structure consistent across tabs while allowing
legacy plain batch payloads to be loaded.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SETTINGS_BUNDLE_SCHEMA = "senoquant.settings"
SETTINGS_BUNDLE_VERSION = 1
SETTINGS_BUNDLE_JSON_SCHEMA_PATH = Path(__file__).with_name(
    "settings_bundle.schema.json"
)


def build_settings_bundle(
    *,
    batch_job: dict | None = None,
    tab_settings: dict | None = None,
    feature_settings: dict | None = None,
    segmentation_runs: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe settings bundle payload.

    Parameters
    ----------
    batch_job : dict or None, optional
        Serialized batch job payload.
    tab_settings : dict or None, optional
        UI tab settings payload (Segmentation/Spots/Batch state).
    feature_settings : dict or None, optional
        Quantification feature export settings payload.
    segmentation_runs : list of dict or None, optional
        Per-layer segmentation metadata entries, including mask file names
        and timestamped run history used to reconstruct run order.

    Returns
    -------
    dict
        JSON-safe bundle payload.
    """
    payload: dict[str, Any] = {
        "schema": SETTINGS_BUNDLE_SCHEMA,
        "version": SETTINGS_BUNDLE_VERSION,
        "batch_job": _json_safe(batch_job) if isinstance(batch_job, dict) else {},
        "tab_settings": (
            _json_safe(tab_settings) if isinstance(tab_settings, dict) else {}
        ),
        "feature_settings": (
            _json_safe(feature_settings)
            if isinstance(feature_settings, dict)
            else {}
        ),
        "segmentation_runs": (
            _json_safe(segmentation_runs)
            if isinstance(segmentation_runs, list)
            else []
        ),
    }
    return payload


def load_settings_bundle_json_schema() -> dict[str, Any]:
    """Load the JSON Schema for ``senoquant.settings`` bundles."""
    with SETTINGS_BUNDLE_JSON_SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return payload
    raise ValueError("Invalid settings bundle schema payload.")


def parse_settings_bundle(payload: object) -> dict[str, Any]:
    """Normalize a loaded JSON payload into the settings bundle shape.

    Parameters
    ----------
    payload : object
        Loaded JSON content.

    Returns
    -------
    dict
        Normalized settings bundle payload.

    Notes
    -----
    Legacy plain batch payloads (``BatchJobConfig.to_dict()`` without the
    envelope)
    are accepted and wrapped into the ``batch_job`` field of the envelope.
    """
    if (
        isinstance(payload, dict)
        and payload.get("schema") == SETTINGS_BUNDLE_SCHEMA
    ):
        legacy_feature = payload.get("feature")
        normalized_tab_settings = payload.get("tab_settings")
        normalized_feature_settings = payload.get("feature_settings")
        if (
            not isinstance(normalized_tab_settings, dict)
            and isinstance(legacy_feature, dict)
            and legacy_feature.get("kind") == "tab_settings"
        ):
            normalized_tab_settings = legacy_feature
        if (
            not isinstance(normalized_feature_settings, dict)
            and isinstance(legacy_feature, dict)
            and legacy_feature.get("kind") != "tab_settings"
        ):
            normalized_feature_settings = legacy_feature
        return build_settings_bundle(
            batch_job=payload.get("batch_job"),
            tab_settings=normalized_tab_settings,
            feature_settings=normalized_feature_settings,
            segmentation_runs=payload.get("segmentation_runs"),
        )
    if isinstance(payload, dict):
        return build_settings_bundle(batch_job=payload)
    return build_settings_bundle()


def _json_safe(value: object):
    """Recursively convert values into JSON-serializable objects."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    return deepcopy(str(value))
