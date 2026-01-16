"""Model wrapper for segmentation resources."""

from __future__ import annotations

import json
from pathlib import Path


class SenoQuantSegmentationModel:
    """Handle per-model storage and metadata paths."""

    def __init__(self, name: str, models_root: Path | None = None) -> None:
        if not name:
            raise ValueError("Model name must be non-empty.")

        self.name = name
        self.models_root = models_root or Path(__file__).parent
        self.model_dir = self.models_root / name
        self.model_dir.mkdir(parents=True, exist_ok=True)

    @property
    def details_path(self) -> Path:
        return self.model_dir / "details.json"

    @property
    def class_path(self) -> Path:
        return self.model_dir / "model.py"

    def load_details(self) -> dict:
        """Load model metadata from the details file.

        Returns
        -------
        dict
            Parsed model metadata dictionary.
        """
        if not self.details_path.exists():
            return {}
        with self.details_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_settings(self) -> list[dict]:
        """Return the settings definitions for this model.

        Returns
        -------
        list[dict]
            Settings definitions for building the UI.
        """
        details = self.load_details()
        settings = details.get("settings", [])
        if isinstance(settings, list):
            return settings
        return []

    def supports_task(self, task: str) -> bool:
        """Return whether the model supports a given task.

        Parameters
        ----------
        task : str
            Task name, such as "nuclear" or "cytoplasmic".

        Returns
        -------
        bool
            True if the task is supported.
        """
        details = self.load_details()
        tasks = details.get("tasks", {})
        task_info = tasks.get(task, {})
        return bool(task_info.get("supported", False))

    def cytoplasmic_input_modes(self) -> list[str]:
        """Return supported input modes for cytoplasmic segmentation.

        Returns
        -------
        list[str]
            Input modes, e.g., "cytoplasmic" or "nuclear+cytoplasmic".
        """
        details = self.load_details()
        tasks = details.get("tasks", {})
        task_info = tasks.get("cytoplasmic", {})
        modes = task_info.get("input_modes", [])
        if isinstance(modes, list):
            return modes
        return []

    def cytoplasmic_nuclear_optional(self) -> bool:
        """Return whether the nuclear channel is optional for cytoplasmic mode.

        Returns
        -------
        bool
            True when the nuclear channel is optional.
        """
        details = self.load_details()
        tasks = details.get("tasks", {})
        task_info = tasks.get("cytoplasmic", {})
        return bool(task_info.get("nuclear_channel_optional", False))
