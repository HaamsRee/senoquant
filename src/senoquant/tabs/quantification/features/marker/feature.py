"""Marker feature UI."""

import numpy as np

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..base import RefreshingComboBox, SenoQuantFeature
from ..roi import ROISection
from .thresholding import THRESHOLD_METHODS, compute_threshold

try:
    from superqt import QDoubleRangeSlider as RangeSlider
except ImportError:  # pragma: no cover - fallback when superqt is unavailable
    try:
        from superqt import QRangeSlider as RangeSlider
    except ImportError:  # pragma: no cover
        RangeSlider = None


class MarkerChannelsDialog(QDialog):
    """Dialog for configuring multiple marker channels."""

    def __init__(self, feature: "MarkerFeature") -> None:
        """Initialize the marker channels dialog.

        Parameters
        ----------
        feature : MarkerFeature
            Marker feature instance owning the dialog.
        """
        super().__init__(feature._tab)
        self._feature = feature
        self._tab = feature._tab
        self._data = feature._data
        self._channels = self._data.setdefault("channels", [])
        self._rows: list[MarkerChannelRow] = []

        self.setWindowTitle("Marker channels")
        layout = QVBoxLayout()

        labels_form = QFormLayout()
        labels_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        labels_combo.currentTextChanged.connect(self._on_labels_changed)
        labels_form.addRow("Segmentation labels", labels_combo)
        labels_widget = QWidget()
        labels_widget.setLayout(labels_form)
        layout.addWidget(labels_widget)

        self._labels_combo = labels_combo
        stored_labels = self._data.get("labels_name")
        if stored_labels:
            labels_combo.setCurrentText(stored_labels)

        self._channels_container = QWidget()
        self._channels_layout = QVBoxLayout()
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(8)
        self._channels_container.setLayout(self._channels_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_area.setWidget(self._channels_container)
        layout.addWidget(scroll_area, 1)

        add_button = QPushButton("Add channel")
        add_button.clicked.connect(self._add_channel)
        layout.addWidget(add_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self._load_channels()

    def _refresh_labels_combo(self, combo: QComboBox) -> None:
        """Refresh labels layer options for the dialog.

        Parameters
        ----------
        combo : QComboBox
            Labels combo box to refresh.
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select labels")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Labels":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _refresh_image_combo(self, combo: QComboBox) -> None:
        """Refresh image layer options for the dialog.

        Parameters
        ----------
        combo : QComboBox
            Image combo box to refresh.
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select image")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Image":
                combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _on_labels_changed(self, text: str) -> None:
        """Store the selected segmentation labels name.

        Parameters
        ----------
        text : str
            Selected labels layer name.
        """
        self._data["labels_name"] = text

    def _load_channels(self) -> None:
        """Build channel rows from stored data."""
        if not self._channels:
            return
        for channel_data in self._channels:
            self._add_channel(channel_data)

    def _add_channel(self, channel_data: dict | None = None) -> None:
        """Add a channel row to the dialog.

        Parameters
        ----------
        channel_data : dict or None
            Channel configuration dictionary.
        """
        if channel_data is None:
            channel_data = {
                "channel": "",
                "threshold_enabled": False,
                "threshold_method": "Otsu",
                "threshold_min": None,
                "threshold_max": None,
            }
            self._channels.append(channel_data)
        row = MarkerChannelRow(self, channel_data)
        self._rows.append(row)
        self._channels_layout.addWidget(row)
        self._renumber_rows()

    def _remove_channel(self, row: "MarkerChannelRow") -> None:
        """Remove a channel row and its stored data.

        Parameters
        ----------
        row : MarkerChannelRow
            Row instance to remove.
        """
        if row not in self._rows:
            return
        self._rows.remove(row)
        if row.data in self._channels:
            self._channels.remove(row.data)
        self._channels_layout.removeWidget(row)
        row.deleteLater()
        self._renumber_rows()

    def _renumber_rows(self) -> None:
        """Update channel row titles after changes."""
        for index, row in enumerate(self._rows, start=1):
            row.update_title(index)


class MarkerChannelRow(QGroupBox):
    """Channel row widget for marker feature channels."""

    def __init__(self, dialog: MarkerChannelsDialog, data: dict) -> None:
        """Initialize a channel row widget.

        Parameters
        ----------
        dialog : MarkerChannelsDialog
            Parent dialog instance.
        data : dict
            Channel configuration dictionary.
        """
        super().__init__()
        self._dialog = dialog
        self._feature = dialog._feature
        self._tab = dialog._tab
        self.data = data

        self.setFlat(True)
        self.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 6px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        channel_form = QFormLayout()
        channel_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        channel_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_image_combo(
                channel_combo
            )
        )
        self._tab._configure_combo(channel_combo)
        channel_combo.currentTextChanged.connect(self._on_channel_changed)
        channel_form.addRow("Channel", channel_combo)
        layout.addLayout(channel_form)

        threshold_checkbox = QCheckBox("Set threshold")
        threshold_checkbox.setEnabled(False)
        threshold_checkbox.toggled.connect(self._toggle_threshold)
        layout.addWidget(threshold_checkbox)

        threshold_container = QWidget()
        threshold_layout = QHBoxLayout()
        threshold_layout.setContentsMargins(0, 0, 0, 0)
        threshold_slider = self._feature._make_range_slider()
        if hasattr(threshold_slider, "valueChanged"):
            threshold_slider.valueChanged.connect(self._on_threshold_slider_changed)
        threshold_min_spin = QDoubleSpinBox()
        threshold_min_spin.setDecimals(2)
        threshold_min_spin.setMinimumWidth(80)
        threshold_min_spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        threshold_min_spin.valueChanged.connect(
            lambda value: self._on_threshold_spin_changed("min", value)
        )

        threshold_max_spin = QDoubleSpinBox()
        threshold_max_spin.setDecimals(2)
        threshold_max_spin.setMinimumWidth(80)
        threshold_max_spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        threshold_max_spin.valueChanged.connect(
            lambda value: self._on_threshold_spin_changed("max", value)
        )

        threshold_slider.setEnabled(False)
        threshold_slider.setVisible(False)
        threshold_min_spin.setEnabled(False)
        threshold_max_spin.setEnabled(False)
        threshold_layout.addWidget(threshold_min_spin)
        threshold_layout.addWidget(threshold_slider, 1)
        threshold_layout.addWidget(threshold_max_spin)
        threshold_container.setLayout(threshold_layout)
        threshold_container.setVisible(False)
        layout.addWidget(threshold_container)

        auto_threshold_container = QWidget()
        auto_threshold_layout = QHBoxLayout()
        auto_threshold_layout.setContentsMargins(0, 0, 0, 0)
        auto_threshold_combo = QComboBox()
        auto_threshold_combo.addItems(list(THRESHOLD_METHODS.keys()))
        self._tab._configure_combo(auto_threshold_combo)
        auto_threshold_combo.currentTextChanged.connect(
            lambda text: self._set_data("threshold_method", text)
        )
        auto_threshold_button = QPushButton("Auto threshold")
        auto_threshold_button.clicked.connect(self._run_auto_threshold)
        auto_threshold_layout.addWidget(auto_threshold_combo, 1)
        auto_threshold_layout.addWidget(auto_threshold_button)
        auto_threshold_container.setLayout(auto_threshold_layout)
        auto_threshold_container.setVisible(False)
        layout.addWidget(auto_threshold_container)

        delete_button = QPushButton("Remove channel")
        delete_button.clicked.connect(lambda: self._dialog._remove_channel(self))
        layout.addWidget(delete_button)

        self.setLayout(layout)

        self._channel_combo = channel_combo
        self._threshold_checkbox = threshold_checkbox
        self._threshold_slider = threshold_slider
        self._threshold_container = threshold_container
        self._threshold_min_spin = threshold_min_spin
        self._threshold_max_spin = threshold_max_spin
        self._auto_threshold_container = auto_threshold_container
        self._auto_threshold_combo = auto_threshold_combo
        self._auto_threshold_button = auto_threshold_button

        self._restore_state()

    def update_title(self, index: int) -> None:
        """Update the title label for the channel row.

        Parameters
        ----------
        index : int
            1-based index used in the title.
        """
        self.setTitle(f"Channel {index}")

    def _set_data(self, key: str, value) -> None:
        """Update the channel data dictionary.

        Parameters
        ----------
        key : str
            Data key to update.
        value : object
            New value to store.
        """
        self.data[key] = value

    def _restore_state(self) -> None:
        """Restore UI state from stored channel data."""
        channel_name = self.data.get("channel", "")
        if channel_name:
            self._channel_combo.setCurrentText(channel_name)
        method = self.data.get("threshold_method") or "Otsu"
        self._auto_threshold_combo.setCurrentText(method)
        enabled = bool(self.data.get("threshold_enabled", False))
        self._threshold_checkbox.setChecked(enabled)
        self._on_channel_changed()

    def _on_channel_changed(self, text: str) -> None:
        """Update threshold controls when channel selection changes.

        Parameters
        ----------
        text : str
            Newly selected channel name.
        """
        self._set_data("channel", text)
        layer = self._feature._get_image_layer_by_name(text)
        if layer is None:
            self._threshold_checkbox.setChecked(False)
            self._threshold_checkbox.setEnabled(False)
            self._set_threshold_controls(False)
            return
        self._threshold_checkbox.setEnabled(True)
        self._feature._set_threshold_range(
            self._threshold_slider,
            layer,
            self._threshold_min_spin,
            self._threshold_max_spin,
        )
        self._set_threshold_controls(self._threshold_checkbox.isChecked())

    def _toggle_threshold(self, enabled: bool) -> None:
        """Toggle threshold controls for this channel.

        Parameters
        ----------
        enabled : bool
            Whether threshold controls should be enabled.
        """
        self._set_data("threshold_enabled", enabled)
        self._set_threshold_controls(enabled)

    def _set_threshold_controls(self, enabled: bool) -> None:
        """Show or hide threshold controls.

        Parameters
        ----------
        enabled : bool
            Whether to show threshold controls.
        """
        self._threshold_slider.setEnabled(enabled)
        self._threshold_slider.setVisible(enabled)
        self._threshold_min_spin.setEnabled(enabled)
        self._threshold_max_spin.setEnabled(enabled)
        self._threshold_container.setVisible(enabled)
        self._auto_threshold_container.setVisible(enabled)
        self._auto_threshold_combo.setEnabled(enabled)
        self._auto_threshold_button.setEnabled(enabled)

    def _on_threshold_slider_changed(self, values) -> None:
        """Sync spin boxes when the slider range changes.

        Parameters
        ----------
        values : tuple
            Updated (min, max) slider values.
        """
        if values is None:
            return
        self._feature._data["threshold_updating"] = True
        self._threshold_min_spin.blockSignals(True)
        self._threshold_max_spin.blockSignals(True)
        self._threshold_min_spin.setValue(values[0])
        self._threshold_max_spin.setValue(values[1])
        self._threshold_min_spin.blockSignals(False)
        self._threshold_max_spin.blockSignals(False)
        self._feature._data["threshold_updating"] = False
        self._set_data("threshold_min", values[0])
        self._set_data("threshold_max", values[1])

    def _on_threshold_spin_changed(self, which: str, value: float) -> None:
        """Sync the slider when a spin box value changes.

        Parameters
        ----------
        which : str
            Identifier for the spin box ("min" or "max").
        value : float
            New spin box value.
        """
        if self._feature._data.get("threshold_updating"):
            return
        min_val = self._threshold_min_spin.value()
        max_val = self._threshold_max_spin.value()
        if min_val > max_val:
            if which == "min":
                max_val = min_val
                self._threshold_max_spin.blockSignals(True)
                self._threshold_max_spin.setValue(max_val)
                self._threshold_max_spin.blockSignals(False)
            else:
                min_val = max_val
                self._threshold_min_spin.blockSignals(True)
                self._threshold_min_spin.setValue(min_val)
                self._threshold_min_spin.blockSignals(False)
        self._feature._data["threshold_updating"] = True
        self._feature._set_slider_values(
            self._threshold_slider, (min_val, max_val)
        )
        self._feature._data["threshold_updating"] = False
        self._set_data("threshold_min", min_val)
        self._set_data("threshold_max", max_val)

    def _run_auto_threshold(self) -> None:
        """Compute an automatic threshold and update the range controls."""
        layer = self._feature._get_image_layer_by_name(
            self._channel_combo.currentText()
        )
        if layer is None:
            return
        method = self._auto_threshold_combo.currentText() or "Otsu"
        try:
            threshold = compute_threshold(layer.data, method)
        except Exception:
            return
        min_val = float(np.nanmin(layer.data))
        max_val = float(np.nanmax(layer.data))
        if min_val == max_val:
            max_val = min_val + 1.0
        threshold = min(max(threshold, min_val), max_val)
        self._feature._set_threshold_range(
            self._threshold_slider,
            layer,
            self._threshold_min_spin,
            self._threshold_max_spin,
        )
        self._feature._data["threshold_updating"] = True
        self._feature._set_slider_values(
            self._threshold_slider, (threshold, max_val)
        )
        self._threshold_min_spin.blockSignals(True)
        self._threshold_min_spin.setValue(threshold)
        self._threshold_min_spin.blockSignals(False)
        self._threshold_max_spin.blockSignals(True)
        self._threshold_max_spin.setValue(max_val)
        self._threshold_max_spin.blockSignals(False)
        self._feature._data["threshold_updating"] = False
        self._set_data("threshold_min", threshold)
        self._set_data("threshold_max", max_val)


class MarkerFeature(SenoQuantFeature):
    """Marker feature controls."""

    feature_type = "Marker"
    order = 10

    def build(self) -> None:
        """Build the marker feature UI."""
        self._build_channels_section()
        roi_section = ROISection(self._tab, self._config)
        roi_section.build()
        self._data["roi_section"] = roi_section

    def on_features_changed(self, configs: list[dict]) -> None:
        """Update ROI titles when feature ordering changes.

        Parameters
        ----------
        configs : list of dict
            Current feature configuration list.
        """
        roi_section = self._data.get("roi_section")
        if roi_section is not None:
            roi_section.update_titles()

    def _build_channels_section(self) -> None:
        """Build the channels button that opens the popup dialog."""
        left_dynamic_layout = self._config.get("left_dynamic_layout")
        if left_dynamic_layout is None:
            return
        button = QPushButton("Add channels")
        button.clicked.connect(self._open_channels_dialog)
        left_dynamic_layout.addWidget(button)
        self._data["channels_button"] = button

    def _open_channels_dialog(self) -> None:
        """Open the channels configuration dialog."""
        dialog = self._data.get("channels_dialog")
        if dialog is None or not isinstance(dialog, QDialog):
            dialog = MarkerChannelsDialog(self)
            self._data["channels_dialog"] = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
