"""Spots feature UI."""

from pathlib import Path

from qtpy.QtWidgets import QCheckBox, QDialog, QPushButton

from ..base import SenoQuantFeature
from ..roi import ROISection
from .config import SpotsFeatureData
from .dialog import SpotsChannelsDialog
from .export import export_spots


class SpotsFeature(SenoQuantFeature):
    """Spots feature controls."""

    feature_type = "Spots"
    order = 20

    def build(self) -> None:
        """Build the spots feature UI."""
        self._build_channels_section()
        data = self._state.data
        if getattr(self._tab, "_enable_rois", True):
            if isinstance(data, SpotsFeatureData):
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
        data = self._state.data
        checkbox = QCheckBox("Export colocalization")
        checkbox.setChecked(
            isinstance(data, SpotsFeatureData) and data.export_colocalization
        )
        checkbox.toggled.connect(self._set_export_colocalization)
        left_dynamic_layout.addWidget(checkbox)
        self._ui["channels_button"] = button
        self._ui["colocalization_checkbox"] = checkbox
        self._update_channels_button_label()

    def _set_export_colocalization(self, checked: bool) -> None:
        """Store colocalization export preference."""
        data = self._state.data
        if not isinstance(data, SpotsFeatureData):
            return
        data.export_colocalization = checked

    def _open_channels_dialog(self) -> None:
        """Open the channels configuration dialog."""
        dialog = self._ui.get("channels_dialog")
        if dialog is None or not isinstance(dialog, QDialog):
            dialog = SpotsChannelsDialog(self)
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
        if isinstance(data, SpotsFeatureData) and (
            data.channels or data.segmentations
        ):
            button.setText("Edit channels")
        else:
            button.setText("Add channels")

    def export(self, temp_dir: Path, export_format: str):
        """Export spots outputs into a temporary directory.

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
        return export_spots(
            self._state,
            temp_dir,
            viewer=self._tab._viewer,
            export_format=export_format,
        )
