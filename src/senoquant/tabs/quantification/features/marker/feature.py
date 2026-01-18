"""Marker feature UI."""

import numpy as np

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from ..base import RefreshingComboBox, SenoQuantFeature
from ..roi import ROISection

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
        self.build_labels_widget("Segmentation labels")
        self._build_channel_section()
        roi_section = ROISection(self._tab, self._config)
        roi_section.build()
        self._config["roi_section"] = roi_section

    def on_features_changed(self, configs: list[dict]) -> None:
        """Update ROI titles when feature ordering changes."""
        roi_section = self._config.get("roi_section")
        if roi_section is not None:
            roi_section.update_titles()

    def _build_channel_section(self) -> None:
        left_dynamic_layout = self._config.get("left_dynamic_layout")
        if left_dynamic_layout is None:
            return

        channel_form = QFormLayout()
        channel_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        channel_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._refresh_image_combo(
                channel_combo
            )
        )
        self._tab._configure_combo(channel_combo)
        channel_combo.currentTextChanged.connect(
            lambda _text: self._on_channel_changed()
        )
        channel_form.addRow("Channel", channel_combo)
        left_dynamic_layout.addLayout(channel_form)

        threshold_checkbox = QCheckBox("Set threshold")
        threshold_checkbox.setEnabled(False)
        threshold_checkbox.toggled.connect(self._toggle_threshold)
        left_dynamic_layout.addWidget(threshold_checkbox)

        threshold_container = QWidget()
        threshold_layout = QHBoxLayout()
        threshold_layout.setContentsMargins(0, 0, 0, 0)
        threshold_slider = self._make_range_slider()
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
        left_dynamic_layout.addWidget(threshold_container)

        self._config["channel_combo"] = channel_combo
        self._config["threshold_checkbox"] = threshold_checkbox
        self._config["threshold_slider"] = threshold_slider
        self._config["threshold_container"] = threshold_container
        self._config["threshold_min_spin"] = threshold_min_spin
        self._config["threshold_max_spin"] = threshold_max_spin
        self._on_channel_changed()

    def _refresh_image_combo(self, combo) -> None:
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

    def _get_image_layer_by_name(self, name: str):
        viewer = self._tab._viewer
        if viewer is None or not name:
            return None
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Image" and layer.name == name:
                return layer
        return None

    def _on_channel_changed(self) -> None:
        combo = self._config.get("channel_combo")
        checkbox = self._config.get("threshold_checkbox")
        slider = self._config.get("threshold_slider")
        min_spin = self._config.get("threshold_min_spin")
        max_spin = self._config.get("threshold_max_spin")
        if combo is None or checkbox is None or slider is None:
            return
        container = self._config.get("threshold_container")
        layer = self._get_image_layer_by_name(combo.currentText())
        if layer is None:
            checkbox.setChecked(False)
            checkbox.setEnabled(False)
            slider.setEnabled(False)
            slider.setVisible(False)
            if min_spin is not None:
                min_spin.setEnabled(False)
            if max_spin is not None:
                max_spin.setEnabled(False)
            if container is not None:
                container.setVisible(False)
            return
        checkbox.setEnabled(True)
        self._set_threshold_range(slider, layer)
        self._toggle_threshold(checkbox.isChecked())

    def _toggle_threshold(self, enabled: bool) -> None:
        slider = self._config.get("threshold_slider")
        container = self._config.get("threshold_container")
        min_spin = self._config.get("threshold_min_spin")
        max_spin = self._config.get("threshold_max_spin")
        if slider is None or container is None:
            return
        slider.setEnabled(enabled)
        slider.setVisible(enabled)
        if min_spin is not None:
            min_spin.setEnabled(enabled)
        if max_spin is not None:
            max_spin.setEnabled(enabled)
        container.setVisible(enabled)

    def _make_range_slider(self):
        if RangeSlider is None:
            return QWidget()
        try:
            return RangeSlider(Qt.Horizontal)
        except TypeError:
            slider = RangeSlider()
            slider.setOrientation(Qt.Horizontal)
            return slider

    def _get_slider_values(self, slider):
        if hasattr(slider, "value"):
            return slider.value()
        if hasattr(slider, "values"):
            return slider.values()
        return None

    def _set_slider_values(self, slider, values) -> None:
        if hasattr(slider, "setValue"):
            try:
                slider.setValue(values)
                return
            except TypeError:
                pass
        if hasattr(slider, "setValues"):
            slider.setValues(values)

    def _set_threshold_range(self, slider, layer) -> None:
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
        min_spin = self._config.get("threshold_min_spin")
        max_spin = self._config.get("threshold_max_spin")
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

    def _on_threshold_slider_changed(self, values) -> None:
        if values is None:
            return
        min_spin = self._config.get("threshold_min_spin")
        max_spin = self._config.get("threshold_max_spin")
        if min_spin is None or max_spin is None:
            return
        self._config["threshold_updating"] = True
        min_spin.blockSignals(True)
        max_spin.blockSignals(True)
        min_spin.setValue(values[0])
        max_spin.setValue(values[1])
        min_spin.blockSignals(False)
        max_spin.blockSignals(False)
        self._config["threshold_updating"] = False

    def _on_threshold_spin_changed(self, which: str, value: float) -> None:
        if self._config.get("threshold_updating"):
            return
        slider = self._config.get("threshold_slider")
        min_spin = self._config.get("threshold_min_spin")
        max_spin = self._config.get("threshold_max_spin")
        if slider is None or min_spin is None or max_spin is None:
            return
        min_val = min_spin.value()
        max_val = max_spin.value()
        if min_val > max_val:
            if which == "min":
                max_val = min_val
                max_spin.blockSignals(True)
                max_spin.setValue(max_val)
                max_spin.blockSignals(False)
            else:
                min_val = max_val
                min_spin.blockSignals(True)
                min_spin.setValue(min_val)
                min_spin.blockSignals(False)
        self._config["threshold_updating"] = True
        self._set_slider_values(slider, (min_val, max_val))
        self._config["threshold_updating"] = False
