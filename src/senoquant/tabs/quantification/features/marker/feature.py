"""Marker feature UI."""

from pathlib import Path

from qtpy.QtWidgets import QDialog, QPushButton

from ..base import SenoQuantFeature
from ..roi import ROISection
from .config import MarkerFeatureData
from .dialog import MarkerChannelsDialog
from .export import export_marker


class MarkerFeature(SenoQuantFeature):
    """Marker feature controls."""

    feature_type = "Markers"
    order = 10

    def build(self) -> None:
        """Build the marker feature UI."""
        self._build_channels_section()
        data = self._state.data
        if getattr(self._tab, "_enable_rois", True):
            if isinstance(data, MarkerFeatureData):
                roi_section = ROISection(self._tab, self._context, data.rois)
            else:
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

    def _build_channels_section(self) -> None:
        """Build the channels button that opens the popup dialog."""
        left_dynamic_layout = self._context.left_dynamic_layout
        button = QPushButton("Add channels")
        button.clicked.connect(self._open_channels_dialog)
        left_dynamic_layout.addWidget(button)
        self._ui["channels_button"] = button
        self._update_channels_button_label()

    def _open_channels_dialog(self) -> None:
        """Open the channels configuration dialog."""
        dialog = self._ui.get("channels_dialog")
        if dialog is None or not isinstance(dialog, QDialog):
            dialog = MarkerChannelsDialog(self)
            dialog.accepted.connect(self._update_channels_button_label)
            self._ui["channels_dialog"] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _update_channels_button_label(self) -> None:
        """Update the channels button label based on saved data."""
        button = self._ui.get("channels_button")
        if button is None:
            return
        data = self._state.data
        if isinstance(data, MarkerFeatureData) and (
            data.channels or data.segmentations
        ):
            button.setText("Edit channels")
        else:
            button.setText("Add channels")

    def _get_image_layer_by_name(self, name: str):
        """Return the image layer with the provided name.

        Parameters
        ----------
        name : str
            Image layer name.

        Returns
        -------
        object or None
            Matching image layer or None if not found.
        """
        viewer = self._tab._viewer
        if viewer is None or not name:
            return None
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Image" and layer.name == name:
                return layer
        return None

    def export(self, temp_dir: Path, export_format: str):
        """Export marker outputs into a temporary directory.

        Parameters
        ----------
        temp_dir : Path
            Temporary directory where outputs should be written.
        export_format : str
            File format requested by the user (``"csv"`` or ``"xlsx"``).

        Returns
        -------
        iterable of Path
            Paths to files produced by the export routine.
        """
        return export_marker(
            self._state,
            temp_dir,
            viewer=self._tab._viewer,
            export_format=export_format,
            enable_thresholds=getattr(self._tab, "_enable_thresholds", True),
        )
