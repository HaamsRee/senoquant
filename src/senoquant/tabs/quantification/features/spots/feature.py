"""Spots feature UI."""

from ..base import SenoQuantFeature


class SpotsFeature(SenoQuantFeature):
    """Spots feature controls."""

    def build(self) -> None:
        """Build the spots feature UI."""
        self._tab._build_labels_widget(self._config, "Spots")
        self._tab._build_roi_section(self._config)
