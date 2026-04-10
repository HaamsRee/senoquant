"""Model wrapper for segmentation resources."""

from __future__ import annotations

from pathlib import Path

class SenoQuantSegmentationModel:
    """Handle per-model storage and metadata paths.

    Parameters
    ----------
    name : str
        Model identifier used for folder creation.
    models_root : pathlib.Path or None
        Optional root folder for model storage.
    """

    def __init__(self, name: str, models_root: Path | None = None) -> None:
        """Initialize the model wrapper and ensure its folder exists."""
        if not name:
            raise ValueError("Model name must be non-empty.")

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
        """Return the path to the model class file."""
        return self.model_dir / "model.py"

    def run(self, **kwargs) -> dict | None:
        """Run the model with the provided inputs and settings.

        Parameters
        ----------
        **kwargs
            Model inputs and settings passed from the UI.

        Returns
        -------
        dict or None
            Result dictionary from the model, or None if not implemented.
        """
        raise NotImplementedError("Model run not implemented.")