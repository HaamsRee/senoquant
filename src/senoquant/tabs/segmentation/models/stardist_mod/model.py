"""StarDist modified nuclear model stub."""

from __future__ import annotations

from ..base import SenoQuantSegmentationModel


class StarDistModModel(SenoQuantSegmentationModel):
    """StarDist modified nuclear model implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("stardist_mod", models_root=models_root)
