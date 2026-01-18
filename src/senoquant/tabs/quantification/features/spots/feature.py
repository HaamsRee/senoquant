"""Spots feature UI."""

from ..base import SenoQuantFeature
from ..roi import ROISection


class SpotsFeature(SenoQuantFeature):
    """Spots feature controls."""

    feature_type = "Spots"
    order = 20

    def build(self) -> None:
        """Build the spots feature UI."""
        self.build_labels_widget("Spots")
        roi_section = ROISection(self._tab, self._config)
        roi_section.build()
        self._config["roi_section"] = roi_section

    def on_features_changed(self, configs: list[dict]) -> None:
        """Update ROI titles when feature ordering changes."""
        roi_section = self._config.get("roi_section")
        if roi_section is not None:
            roi_section.update_titles()
