"""CPSAM segmentation model stub."""

from __future__ import annotations

from ..model import SenoQuantSegmentationModel


class CPSAMModel(SenoQuantSegmentationModel):
    """CPSAM segmentation model implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("cpsam", models_root=models_root)
