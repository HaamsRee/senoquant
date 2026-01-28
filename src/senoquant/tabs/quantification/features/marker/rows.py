"""Marker channels dialog rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from senoquant.utils import layer_data_asarray
from ..base import RefreshingComboBox
from .thresholding import THRESHOLD_METHODS, compute_threshold
from .config import MarkerChannelConfig, MarkerSegmentationConfig

if TYPE_CHECKING:
    from .dialog import MarkerChannelsDialog

try:
    from superqt import QDoubleRangeSlider as RangeSlider
except ImportError:  # pragma: no cover - fallback when superqt is unavailable
    try:
        from superqt import QRangeSlider as RangeSlider
    except ImportError:  # pragma: no cover
        RangeSlider = None


class MarkerSegmentationRow(QGroupBox):
    """Segmentation row widget for marker segmentations."""

    def __init__(
        self, dialog: MarkerChannelsDialog, data: MarkerSegmentationConfig
    ) -> None:
        """Initialize a segmentation row widget.

        Parameters
        ----------
        dialog : MarkerChannelsDialog
            Parent dialog instance.
        data : MarkerSegmentationConfig
            Segmentation configuration data.
        """
        super().__init__()
        self._dialog = dialog
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

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        labels_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_labels_combo(
                labels_combo
            )
        )
        self._tab._configure_combo(labels_combo)
        labels_combo.currentTextChanged.connect(
            lambda text: self._set_data("label", text)
        )
        form_layout.addRow("Labels", labels_combo)
        layout.addLayout(form_layout)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(
            lambda: self._dialog._remove_segmentation(self)
        )
        layout.addWidget(delete_button)

        self._labels_combo = labels_combo
        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._restore_state()

    def update_title(self, index: int) -> None:
        """Update the title label for the segmentation row.

        Parameters
        ----------
        index : int
            0-based index used in the title.
        """
        self.setTitle(f"Segmentation {index}")

    def _set_data(self, key: str, value) -> None:
        """Update the segmentation data model."""
        setattr(self.data, key, value)

    def _restore_state(self) -> None:
        """Restore UI state from stored segmentation data."""
        label_name = self.data.label
        if label_name:
            self._labels_combo.setCurrentText(label_name)


class MarkerChannelRow(QGroupBox):
    """Channel row widget for marker feature channels."""

    def __init__(
        self, dialog: MarkerChannelsDialog, data: MarkerChannelConfig
    ) -> None:
        """Initialize a channel row widget.

        Parameters
        ----------
        dialog : MarkerChannelsDialog
            Parent dialog instance.
        data : MarkerChannelConfig
            Channel configuration data.
        """
        super().__init__()
        self._dialog = dialog
        self._feature = dialog._feature
        self._tab = dialog._tab
        self.data = data
        self._threshold_updating = False
        self._thresholds_enabled = getattr(self._tab, "_enable_thresholds", True)

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
        name_input = QLineEdit()
        name_input.setPlaceholderText("Channel name")
        name_input.setMinimumWidth(160)
        name_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        name_input.textChanged.connect(
            lambda text: self._set_data("name", text)
        )
        channel_combo = RefreshingComboBox(
            refresh_callback=lambda combo_ref=None: self._dialog._refresh_image_combo(
                channel_combo
            )
        )
        self._tab._configure_combo(channel_combo)
        channel_combo.currentTextChanged.connect(self._on_channel_changed)
        channel_form.addRow("Name", name_input)
        channel_form.addRow("Channel", channel_combo)
        layout.addLayout(channel_form)

        threshold_checkbox = QCheckBox("Set threshold")
        threshold_checkbox.setEnabled(False)
        threshold_checkbox.toggled.connect(self._toggle_threshold)
        layout.addWidget(threshold_checkbox)

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
        layout.addWidget(threshold_container)

        auto_threshold_container = QWidget()
        auto_threshold_layout = QHBoxLayout()
        auto_threshold_layout.setContentsMargins(0, 0, 0, 0)
        auto_threshold_combo = QComboBox()
        auto_threshold_combo.addItems(
            ["Manual", *list(THRESHOLD_METHODS.keys())]
        )
        self._tab._configure_combo(auto_threshold_combo)
        auto_threshold_combo.currentTextChanged.connect(
            self._on_threshold_method_changed
        )
        auto_threshold_button = QPushButton("Auto threshold")
        auto_threshold_button.clicked.connect(self._run_auto_threshold)
        auto_threshold_layout.addWidget(auto_threshold_combo, 1)
        auto_threshold_layout.addWidget(auto_threshold_button)
        auto_threshold_container.setLayout(auto_threshold_layout)
        auto_threshold_container.setVisible(False)
        layout.addWidget(auto_threshold_container)

        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(lambda: self._dialog._remove_channel(self))
        layout.addWidget(delete_button)

        self.setLayout(layout)

        self._channel_combo = channel_combo
        self._name_input = name_input
        self._threshold_checkbox = threshold_checkbox
        self._threshold_slider = threshold_slider
        self._threshold_container = threshold_container
        self._threshold_min_spin = threshold_min_spin
        self._threshold_max_spin = threshold_max_spin
        self._auto_threshold_container = auto_threshold_container
        self._auto_threshold_combo = auto_threshold_combo
        self._auto_threshold_button = auto_threshold_button
        self._auto_thresholding = False
        self._threshold_min_bound: float | None = None
        self._threshold_max_bound: float | None = None

        if not self._thresholds_enabled:
            threshold_checkbox.setVisible(False)
            threshold_container.setVisible(False)
            auto_threshold_container.setVisible(False)
            threshold_checkbox.setEnabled(False)
            auto_threshold_button.setEnabled(False)

        self._restore_state()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_title(self, index: int) -> None:
        """Update the title label for the channel row.

        Parameters
        ----------
        index : int
            0-based index used in the title.
        """
        self.setTitle(f"Channel {index}")

    def _set_data(self, key: str, value) -> None:
        """Update the channel data model.

        Parameters
        ----------
        key : str
            Data key to update.
        value : object
            New value to store.
        """
        setattr(self.data, key, value)

    def _restore_state(self) -> None:
        """Restore UI state from stored channel data."""
        channel_label = self.data.name
        if channel_label:
            self._name_input.setText(channel_label)
        channel_name = self.data.channel
        if channel_name:
            self._channel_combo.setCurrentText(channel_name)
        method = self.data.threshold_method or "Manual"
        self._auto_threshold_combo.setCurrentText(method)
        enabled = bool(self.data.threshold_enabled)
        self._threshold_checkbox.setChecked(enabled)
        self._on_channel_changed(self._channel_combo.currentText())
        if not self._thresholds_enabled:
            self._set_data("threshold_enabled", False)
            self._set_data("threshold_method", "Manual")
            self._set_data("threshold_min", None)
            self._set_data("threshold_max", None)

    def _layer_has_data(self, layer) -> bool:
        data = getattr(layer, "data", None)
        if data is None:
            return False
        try:
            array = np.asarray(data)
        except Exception:
            return False
        if array.size == 0:
            return False
        if array.dtype == object and array.size == 1 and array.flat[0] is None:
            return False
        return True

    def _disable_threshold_controls(self) -> None:
        self._threshold_min_bound = None
        self._threshold_max_bound = None
        self._threshold_checkbox.blockSignals(True)
        self._threshold_checkbox.setChecked(False)
        self._threshold_checkbox.blockSignals(False)
        self._set_data("threshold_enabled", False)
        self._threshold_checkbox.setEnabled(False)
        self._auto_threshold_button.setEnabled(False)
        self._set_threshold_controls(False)

    def _on_channel_changed(self, text: str | None = None) -> None:
        """Update threshold controls when channel selection changes.

        Parameters
        ----------
        text : str
            Newly selected channel name.
        """
        if text is None:
            text = self._channel_combo.currentText()
        self._set_data("channel", text)
        if not self._thresholds_enabled:
            self._disable_threshold_controls()
            return
        layer = self._feature._get_image_layer_by_name(text)
        if layer is None or not self._layer_has_data(layer):
            self._disable_threshold_controls()
            return
        self._threshold_checkbox.setEnabled(True)
        self._set_threshold_range(
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
        if not self._thresholds_enabled:
            return
        self._set_data("threshold_enabled", enabled)
        self._set_threshold_controls(enabled)

    def _set_threshold_controls(self, enabled: bool) -> None:
        """Show or hide threshold controls.

        Parameters
        ----------
        enabled : bool
            Whether to show threshold controls.
        """
        if not self._thresholds_enabled:
            enabled = False
        self._threshold_slider.setEnabled(enabled)
        self._threshold_slider.setVisible(enabled)
        self._threshold_min_spin.setEnabled(enabled)
        self._threshold_max_spin.setEnabled(enabled)
        self._threshold_container.setVisible(enabled)
        self._auto_threshold_container.setVisible(enabled)
        self._auto_threshold_combo.setEnabled(enabled)
        self._auto_threshold_button.setEnabled(
            enabled and self._auto_threshold_combo.currentText() != "Manual"
        )

    def _on_threshold_method_changed(self, text: str) -> None:
        """Handle changes to the thresholding method selection."""
        if not self._thresholds_enabled:
            return
        self._set_data("threshold_method", text)
        if text == "Manual":
            self._auto_threshold_button.setEnabled(False)
            return
        self._auto_threshold_button.setEnabled(
            self._threshold_checkbox.isChecked()
        )

    def _on_threshold_slider_changed(self, values) -> None:
        """Sync spin boxes when the slider range changes.

        Parameters
        ----------
        values : tuple
            Updated (min, max) slider values.
        """
        if values is None or self._threshold_updating:
            return
        self._threshold_updating = True
        self._threshold_min_spin.blockSignals(True)
        self._threshold_max_spin.blockSignals(True)
        self._threshold_min_spin.setValue(values[0])
        self._threshold_max_spin.setValue(values[1])
        self._threshold_min_spin.blockSignals(False)
        self._threshold_max_spin.blockSignals(False)
        self._threshold_updating = False
        self._set_data("threshold_min", float(values[0]))
        self._set_data("threshold_max", float(values[1]))
        self._update_layer_contrast_limits(values)
        self._ensure_manual_threshold_mode()

    def _on_threshold_spin_changed(self, which: str, value: float) -> None:
        """Sync the slider when a spin box value changes.

        Parameters
        ----------
        which : str
            Identifier for the spin box ("min" or "max").
        value : float
            New spin box value.
        """
        if self._threshold_updating:
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
        self._threshold_updating = True
        self._set_slider_values(
            self._threshold_slider, (min_val, max_val)
        )
        self._threshold_updating = False
        self._set_data("threshold_min", float(min_val))
        self._set_data("threshold_max", float(max_val))
        self._update_layer_contrast_limits((min_val, max_val))
        self._ensure_manual_threshold_mode()

    def _run_auto_threshold(self) -> None:
        """Compute an automatic threshold and update the range controls."""
        if not self._thresholds_enabled:
            return
        layer = self._feature._get_image_layer_by_name(
            self._channel_combo.currentText()
        )
        if layer is None or not self._layer_has_data(layer):
            return
        method = self._auto_threshold_combo.currentText() or "Otsu"
        if method == "Manual":
            return
        try:
            threshold = compute_threshold(layer_data_asarray(layer), method)
        except Exception:
            return
        min_val = self._threshold_min_bound
        max_val = self._threshold_max_bound
        if min_val is None or max_val is None:
            self._set_threshold_range(
                self._threshold_slider,
                layer,
                self._threshold_min_spin,
                self._threshold_max_spin,
            )
            min_val = self._threshold_min_bound
            max_val = self._threshold_max_bound
        if min_val is None or max_val is None:
            return
        threshold = min(max(threshold, min_val), max_val)
        self._auto_thresholding = True
        try:
            self._threshold_updating = True
            self._set_slider_values(
                self._threshold_slider, (threshold, max_val)
            )
            self._threshold_min_spin.blockSignals(True)
            self._threshold_min_spin.setValue(threshold)
            self._threshold_min_spin.blockSignals(False)
            self._threshold_max_spin.blockSignals(True)
            self._threshold_max_spin.setValue(max_val)
            self._threshold_max_spin.blockSignals(False)
            self._threshold_updating = False
            self._set_data("threshold_min", float(threshold))
            self._set_data("threshold_max", float(max_val))
            self._update_layer_contrast_limits((threshold, max_val))
        finally:
            self._auto_thresholding = False

    def _ensure_manual_threshold_mode(self) -> None:
        """Switch to manual mode after user-adjusted threshold changes."""
        if not self._thresholds_enabled:
            return
        if not self._threshold_checkbox.isChecked():
            return
        if self._auto_thresholding:
            return
        if self._auto_threshold_combo.currentText() == "Manual":
            return
        self._auto_threshold_combo.blockSignals(True)
        self._auto_threshold_combo.setCurrentText("Manual")
        self._auto_threshold_combo.blockSignals(False)
        self._set_data("threshold_method", "Manual")
        self._auto_threshold_button.setEnabled(False)

    def _update_layer_contrast_limits(self, values) -> None:
        """Sync the image layer contrast limits with the threshold values.

        Parameters
        ----------
        values : tuple
            (min, max) values to apply as contrast limits.
        """
        layer = self._feature._get_image_layer_by_name(
            self._channel_combo.currentText()
        )
        if layer is None:
            return
        try:
            layer.contrast_limits = [float(values[0]), float(values[1])]
        except Exception:
            return

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
        if not self._layer_has_data(layer):
            self._disable_threshold_controls()
            return
        min_val, max_val = self._get_threshold_bounds(layer)
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

    def _get_threshold_bounds(self, layer) -> tuple[float, float]:
        """Return threshold bounds based on the layer contrast range.

        Parameters
        ----------
        layer : object
            Napari image layer providing contrast bounds and data.

        Returns
        -------
        tuple of float
            Minimum and maximum bounds for the threshold controls.

        Notes
        -----
        The computed bounds are cached on the row instance to avoid repeated
        scans of large images when auto-thresholding runs.
        """
        contrast = getattr(layer, "contrast_limits_range", None)
        if contrast is not None and len(contrast) == 2:
            min_val, max_val = float(contrast[0]), float(contrast[1])
        else:
            data = layer_data_asarray(layer)
            min_val = float(np.nanmin(data))
            max_val = float(np.nanmax(data))
        if min_val == max_val:
            max_val = min_val + 1.0
        self._threshold_min_bound = min_val
        self._threshold_max_bound = max_val
        return min_val, max_val
