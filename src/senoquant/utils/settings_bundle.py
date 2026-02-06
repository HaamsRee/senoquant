"""Shared settings bundle serialization helpers.

This module defines the ``senoquant.settings`` envelope used across:
- Batch profile save/load.
- Quantification feature export settings payloads.

The envelope keeps payload structure consistent across tabs while allowing
legacy plain batch profiles to be loaded.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


SETTINGS_BUNDLE_SCHEMA = "senoquant.settings"
SETTINGS_BUNDLE_VERSION = 1


def build_settings_bundle(
    *,
    batch_job: dict | None = None,
    feature: dict | None = None,
    segmentation_runs: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe settings bundle payload.

    Parameters
    ----------
    batch_job : dict or None, optional
        Serialized batch job payload.
    feature : dict or None, optional
        Feature export payload.
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
        "feature": _json_safe(feature) if isinstance(feature, dict) else {},
        "segmentation_runs": (
            _json_safe(segmentation_runs)
            if isinstance(segmentation_runs, list)
            else []
        ),
    }
    return payload


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
    Legacy batch profiles that are plain ``BatchJobConfig.to_dict()`` payloads
    are accepted and wrapped into the ``batch_job`` field of the envelope.
    """
    if (
        isinstance(payload, dict)
        and payload.get("schema") == SETTINGS_BUNDLE_SCHEMA
    ):
        return build_settings_bundle(
            batch_job=payload.get("batch_job"),
            feature=payload.get("feature"),
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
