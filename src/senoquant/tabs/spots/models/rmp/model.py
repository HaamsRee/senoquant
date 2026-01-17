"""RMP spot detector stub."""

from __future__ import annotations

from ..model import SenoQuantSpotDetector


class RMPDetector(SenoQuantSpotDetector):
    """RMP spot detector implementation."""

    def __init__(self, models_root=None) -> None:
        super().__init__("rmp", models_root=models_root)
