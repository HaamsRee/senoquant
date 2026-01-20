"""Marker channels dialog rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

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

from ..base import RefreshingComboBox
from .thresholding import THRESHOLD_METHODS, compute_threshold
from .config import MarkerChannelConfig, MarkerSegmentationConfig

if TYPE_CHECKING:
    from .dialog import MarkerChannelsDialog


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
            1-based index used in the title.
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

        self._restore_state()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def update_title(self, index: int) -> None:
        """Update the title label for the channel row.

        Parameters
        ----------
        index : int
            1-based index used in the title.
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
        method = self.data.threshold_method or "Otsu"
        self._auto_threshold_combo.setCurrentText(method)
        enabled = bool(self.data.threshold_enabled)
        self._threshold_checkbox.setChecked(enabled)
        self._on_channel_changed(self._channel_combo.currentText())

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
        self._feature._set_slider_values(
            self._threshold_slider, (min_val, max_val)
        )
        self._threshold_updating = False
        self._set_data("threshold_min", float(min_val))
        self._set_data("threshold_max", float(max_val))

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
        self._threshold_updating = True
        self._feature._set_slider_values(
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
