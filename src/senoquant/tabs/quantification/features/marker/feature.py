"""Marker feature UI."""

from pathlib import Path

from qtpy.QtWidgets import QCheckBox, QDialog, QPushButton

from ..base import SenoQuantFeature
from ..roi import ROISection
from .config import MarkerFeatureData
from .dialog import MarkerChannelsDialog
from .export import export_marker
from .postprocess import postprocess_marker_merged_wide


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
        button = QPushButton("Add channel(s)")
        button.clicked.connect(self._open_channels_dialog)
        left_dynamic_layout.addWidget(button)
        checkbox = QCheckBox("Merge tables across segmentations")
        data = self._state.data
        checked = True
        if isinstance(data, MarkerFeatureData):
            checked = data.merge_tables_across_segmentations
        checkbox.setChecked(bool(checked))
        checkbox.toggled.connect(self._set_merge_tables_across_segmentations)
        left_dynamic_layout.addWidget(checkbox)
        self._ui["channels_button"] = button
        self._ui["merge_tables_checkbox"] = checkbox
        self._update_channels_button_label()
        self._update_merge_checkbox_state()

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
            button.setText("Edit channel(s)")
        else:
            button.setText("Add channel(s)")

    def _set_merge_tables_across_segmentations(self, checked: bool) -> None:
        """Store marker merged-table export preference."""
        data = self._state.data
        if not isinstance(data, MarkerFeatureData):
            return
        data.merge_tables_across_segmentations = bool(checked)

    def _update_merge_checkbox_state(self) -> None:
        """Enable marker table merge only when multiple segmentations exist."""
        checkbox = self._ui.get("merge_tables_checkbox")
        data = self._state.data
        if checkbox is None or not isinstance(data, MarkerFeatureData):
            return
        valid_segmentations = sum(
            1 for segmentation in data.segmentations if segmentation.label.strip()
        )
        checkbox.setEnabled(valid_segmentations >= 2)

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
        outputs = list(
            export_marker(
                self._state,
                temp_dir,
                viewer=self._tab._viewer,
                export_format=export_format,
                enable_thresholds=getattr(self._tab, "_enable_thresholds", True),
            )
        )
        return postprocess_marker_merged_wide(
            self._state,
            temp_dir,
            outputs,
            viewer=self._tab._viewer,
            export_format=export_format,
        )
