"""Feature UI base classes for quantification."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..frontend import QuantificationTab


class SenoQuantFeature:
    """Base class for quantification feature UI."""

    def __init__(self, tab: "QuantificationTab", config: dict) -> None:
        self._tab = tab
        self._config = config

    def build(self) -> None:
        """Build the UI for this feature."""
        raise NotImplementedError
