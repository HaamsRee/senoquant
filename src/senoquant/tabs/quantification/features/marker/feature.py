"""Marker feature UI."""

import numpy as np

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDoubleSpinBox, QDialog, QPushButton, QWidget

from ..base import SenoQuantFeature
from ..roi import ROISection
from .config import MarkerFeatureData
from .dialog import MarkerChannelsDialog

try:
    from superqt import QDoubleRangeSlider as RangeSlider
except ImportError:  # pragma: no cover - fallback when superqt is unavailable
    try:
        from superqt import QRangeSlider as RangeSlider
    except ImportError:  # pragma: no cover
        RangeSlider = None


class MarkerFeature(SenoQuantFeature):
    """Marker feature controls."""

    feature_type = "Marker"
    order = 10

    def build(self) -> None:
        """Build the marker feature UI."""
        self._build_channels_section()
        data = self._state.data
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

    def _make_range_slider(self):
        """Create a horizontal range slider if available.

        Returns
        -------
        QWidget
            Range slider widget or a placeholder QWidget when unavailable.
        """
        if RangeSlider is None:
            return QWidget()
        try:
            return RangeSlider(Qt.Horizontal)
        except TypeError:
            slider = RangeSlider()
            slider.setOrientation(Qt.Horizontal)
            return slider

    def _set_slider_values(self, slider, values) -> None:
        """Set the range values on a slider.

        Parameters
        ----------
        slider : QWidget
            Range slider widget.
        values : tuple
            (min, max) values to apply to the slider.
        """
        if hasattr(slider, "setValue"):
            try:
                slider.setValue(values)
                return
            except TypeError:
                pass
        if hasattr(slider, "setValues"):
            slider.setValues(values)

    def _set_threshold_range(
        self, slider, layer, min_spin: QDoubleSpinBox | None,
        max_spin: QDoubleSpinBox | None
    ) -> None:
        """Set slider bounds using the selected image layer.

        Parameters
        ----------
        slider : QWidget
            Range slider widget.
        layer : object
            Napari image layer providing intensity bounds.
        min_spin : QDoubleSpinBox or None
            Spin box that displays the minimum threshold value.
        max_spin : QDoubleSpinBox or None
            Spin box that displays the maximum threshold value.
        """
        if not hasattr(slider, "setMinimum"):
            return
        data = layer.data
        min_val = float(np.nanmin(data))
        max_val = float(np.nanmax(data))
        if min_val == max_val:
            max_val = min_val + 1.0
        if hasattr(slider, "setRange"):
            slider.setRange(min_val, max_val)
        else:
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
        self._set_slider_values(slider, (min_val, max_val))
        if min_spin is not None:
            min_spin.blockSignals(True)
            min_spin.setRange(min_val, max_val)
            min_spin.setValue(min_val)
            min_spin.blockSignals(False)
        if max_spin is not None:
            max_spin.blockSignals(True)
            max_spin.setRange(min_val, max_val)
            max_spin.setValue(max_val)
            max_spin.blockSignals(False)
