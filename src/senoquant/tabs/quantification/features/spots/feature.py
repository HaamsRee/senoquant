"""Spots feature UI."""

from ..base import SenoQuantFeature
from ..roi import ROISection
from ...config import SpotsFeatureData


class SpotsFeature(SenoQuantFeature):
    """Spots feature controls."""

    feature_type = "Spots"
    order = 20

    def build(self) -> None:
        """Build the spots feature UI."""
        data = self._state.data
        if isinstance(data, SpotsFeatureData):
            self.build_labels_widget(
                "Spots",
                get_value=lambda: data.labels,
                set_value=lambda text: setattr(data, "labels", text),
            )
            roi_section = ROISection(self._tab, self._context, data.rois)
        else:
            self.build_labels_widget("Spots")
            roi_section = ROISection(self._tab, self._context, [])
        roi_section.build()
        self._ui["roi_section"] = roi_section

    def on_features_changed(self, configs: list) -> None:
        """Update ROI titles when feature ordering changes.

        Parameters
        ----------
        configs : list of FeatureUIContext
            Current feature contexts.
        """
        roi_section = self._ui.get("roi_section")
        if roi_section is not None:
            roi_section.update_titles()
