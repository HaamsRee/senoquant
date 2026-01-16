"""Model wrapper for segmentation resources."""

from __future__ import annotations

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
