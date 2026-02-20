"""Backend helpers for shared settings persistence in the Settings tab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qtpy.QtCore import QObject

from senoquant.utils.path_io import is_remote, normalize_uri, write_json
from senoquant.utils.settings_bundle import build_settings_bundle, parse_settings_bundle


class SettingsBackend(QObject):
    """Read and write unified settings bundle payloads."""

    SETTINGS_FILENAME = "senoquant_settings.json"

    def __init__(self) -> None:
        """Initialize the backend."""
        super().__init__()

    @classmethod
    def default_settings_filename(cls) -> str:
        """Return the default JSON filename used for settings exports."""
        return cls.SETTINGS_FILENAME

    def build_bundle(
        self,
        *,
        segmentation: dict | None = None,
        spots: dict | None = None,
        batch_job: dict | None = None,
    ) -> dict[str, Any]:
        """Build a normalized settings bundle payload for UI settings.

        Parameters
        ----------
        segmentation : dict or None, optional
            Segmentation tab settings state payload.
        spots : dict or None, optional
            Spots tab settings state payload.
        batch_job : dict or None, optional
            Batch tab settings payload, when available.

        Returns
        -------
        dict of str to Any
            Canonical ``senoquant.settings`` bundle payload.
        """
        feature_payload: dict[str, Any] = {
            "kind": "tab_settings",
            "segmentation": segmentation if isinstance(segmentation, dict) else {},
            "spots": spots if isinstance(spots, dict) else {},
        }
        return build_settings_bundle(
            batch_job=batch_job if isinstance(batch_job, dict) else {},
            tab_settings=feature_payload,
        )

    @staticmethod
    def parse_bundle(payload: object) -> dict[str, Any]:
        """Parse raw JSON payload into a normalized settings bundle."""
        return parse_settings_bundle(payload)

    def load_bundle(self, path: str | Path) -> dict[str, Any]:
        """Load and normalize a settings bundle from disk."""
        bundle_path = normalize_uri(path)
        if is_remote(bundle_path):
            try:
                import fsspec
            except Exception as exc:  # pragma: no cover - optional dependency
                raise ImportError("fsspec is required for remote settings paths.") from exc
            with fsspec.open(bundle_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return self.parse_bundle(payload)
        local_path = Path(bundle_path).expanduser()
        with local_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return self.parse_bundle(payload)

    def save_bundle(self, path: str | Path, payload: dict[str, Any]) -> str:
        """Write a settings bundle payload to disk."""
        bundle_path = normalize_uri(path)
        return write_json(bundle_path, payload)
