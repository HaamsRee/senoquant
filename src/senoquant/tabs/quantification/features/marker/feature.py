"""Marker feature UI."""

from ..base import SenoQuantFeature


class MarkerFeature(SenoQuantFeature):
    """Marker feature controls."""

    def build(self) -> None:
        """Build the marker feature UI."""
        self._tab._build_labels_widget(
            self._config, "Segmentation labels"
        )
        self._tab._build_marker_channel_section(self._config)
        self._tab._build_roi_section(self._config)
