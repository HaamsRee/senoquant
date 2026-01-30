"""Base class for spot detector implementations."""

from __future__ import annotations

import json
from pathlib import Path


class SenoQuantSpotDetector:
    """Handle per-detector storage and metadata paths.

    Parameters
    ----------
    name : str
        Detector identifier used for folder creation.
    models_root : pathlib.Path or None
        Optional root folder for detector storage.
    """

    def __init__(self, name: str, models_root: Path | None = None) -> None:
        """Initialize the detector wrapper and ensure its folder exists."""
        if not name:
            raise ValueError("Detector name must be non-empty.")

        self.name = name
        self.models_root = models_root or Path(__file__).parent
        self.model_dir = self.models_root / name
        self.model_dir.mkdir(parents=True, exist_ok=True)

    @property
    def details_path(self) -> Path:
        """Return the path to the details JSON file."""
        return self.model_dir / "details.json"

    @property
    def class_path(self) -> Path:
        """Return the path to the detector class file."""
        return self.model_dir / "model.py"

    def load_details(self) -> dict:
        """Load detector metadata from the details file.

        Returns
        -------
        dict
            Parsed detector metadata dictionary.
        """
        if not self.details_path.exists():
            return {}
        with self.details_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_settings(self) -> list[dict]:
        """Return the settings definitions for this detector.

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

    def display_order(self) -> float | None:
        """Return the optional display ordering for this detector.

        Returns
        -------
        float or None
            Numeric ordering value if specified in details.json.
        """
        details = self.load_details()
        order = details.get("order")
        if isinstance(order, (int, float)):
            return float(order)
        if isinstance(order, str):
            try:
                return float(order)
            except ValueError:
                return None
        return None

    def run(self, **kwargs) -> None:
        """Run the detector with the provided inputs and settings.

        Parameters
        ----------
        **kwargs
            Detector inputs and settings passed from the UI.
        """
        raise NotImplementedError("Spot detector run not implemented.")
