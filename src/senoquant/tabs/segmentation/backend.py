"""Backend logic for the Segmentation tab."""

from __future__ import annotations

from pathlib import Path

from .models import SenoQuantSegmentationModel


class SegmentationBackend:
    def __init__(self, models_root: Path | None = None) -> None:
        self._models_root = models_root
        self._models: dict[str, SenoQuantSegmentationModel] = {}

    def get_model(self, name: str) -> SenoQuantSegmentationModel:
        model = self._models.get(name)
        if model is None:
            model = SenoQuantSegmentationModel(name, self._models_root)
            self._models[name] = model
        return model
