"""Cytoplasmic-only model stub."""

from __future__ import annotations

from ..base import SenoQuantSegmentationModel


class CytoOnlyModel(SenoQuantSegmentationModel):
    """Cytoplasmic-only model implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("cyto_only", models_root=models_root)
