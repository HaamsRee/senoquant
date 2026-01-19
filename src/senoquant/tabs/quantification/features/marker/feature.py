"""Marker feature UI."""

import numpy as np

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..base import RefreshingComboBox, SenoQuantFeature
from ..roi import ROISection
from .thresholding import THRESHOLD_METHODS, compute_threshold
from ...config import (
    MarkerChannelConfig,
    MarkerFeatureData,
    MarkerSegmentationConfig,
)

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
        data = feature._state.data
        if not isinstance(data, MarkerFeatureData):
            data = MarkerFeatureData()
            feature._state.data = data
        self._data = data
        self._segmentations = data.segmentations
        self._channels = data.channels
        self._rows: list[MarkerChannelRow] = []
        self._segmentation_rows: list[MarkerSegmentationRow] = []
        self._layout_watch_timer: QTimer | None = None
        self._layout_last_sizes: dict[str, tuple[int, int]] = {}

        self.setWindowTitle("Marker channels")
        self.setMinimumSize(720, 640)
        layout = QVBoxLayout()

        segmentations_section = self._build_segmentations_section()
        layout.addWidget(segmentations_section)

        self._channels_container = QWidget()
        self._channels_layout = QVBoxLayout()
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(8)
        self._channels_container.setLayout(self._channels_layout)

        frame = QGroupBox("Channels")
        frame.setFlat(True)
        frame.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 8px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        self._channels_scroll_area = QScrollArea()
        self._channels_scroll_area.setWidgetResizable(True)
        self._channels_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._channels_scroll_area.setWidget(self._channels_container)

        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(10, 12, 10, 10)
        frame_layout.addWidget(self._channels_scroll_area)
        frame.setLayout(frame_layout)
        layout.addWidget(frame, 1)

        add_button = QPushButton("Add channel")
        add_button.clicked.connect(self._add_channel)
        layout.addWidget(add_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self._load_segmentations()
        self._load_channels()
        self._start_layout_watch()

    def _build_segmentations_section(self) -> QGroupBox:
        """Create the segmentations section with add/remove controls."""
        section = QGroupBox("Segmentations")
        section.setFlat(True)
        section.setStyleSheet(
            "QGroupBox {"
            "  margin-top: 8px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

        self._segmentations_container = QWidget()
        self._segmentations_layout = QVBoxLayout()
        self._segmentations_layout.setContentsMargins(0, 0, 0, 0)
        self._segmentations_layout.setSpacing(8)
        self._segmentations_container.setLayout(self._segmentations_layout)

        self._segmentations_scroll_area = QScrollArea()
        self._segmentations_scroll_area.setWidgetResizable(True)
        self._segmentations_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._segmentations_scroll_area.setWidget(
            self._segmentations_container
        )

        add_button = QPushButton("Add segmentation")
        add_button.clicked.connect(self._add_segmentation)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(10, 12, 10, 10)
        section_layout.addWidget(self._segmentations_scroll_area)
        section_layout.addWidget(add_button)
        section.setLayout(section_layout)

        return section

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

    def _load_segmentations(self) -> None:
        """Build segmentation rows from stored data."""
        if not self._segmentations:
            return
        for segmentation_data in self._segmentations:
            if not isinstance(segmentation_data, MarkerSegmentationConfig):
                continue
            self._add_segmentation(segmentation_data)

    def _load_channels(self) -> None:
        """Build channel rows from stored data."""
        if not self._channels:
            return
        for channel_data in self._channels:
            if not isinstance(channel_data, MarkerChannelConfig):
                continue
            self._add_channel(channel_data)

    def _add_channel(self, channel_data: MarkerChannelConfig | None = None) -> None:
        """Add a channel row to the dialog.

        Parameters
        ----------
        channel_data : MarkerChannelConfig or None
            Channel configuration data.
        """
        if isinstance(channel_data, bool):
            channel_data = None
        if not isinstance(channel_data, MarkerChannelConfig):
            channel_data = MarkerChannelConfig()
            self._channels.append(channel_data)
        row = MarkerChannelRow(self, channel_data)
        self._rows.append(row)
        self._channels_layout.addWidget(row)
        self._renumber_rows()
        self._schedule_layout_update()

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
        self._schedule_layout_update()

    def _renumber_rows(self) -> None:
        """Update channel row titles after changes."""
        for index, row in enumerate(self._rows, start=1):
            row.update_title(index)

    def _add_segmentation(
        self, segmentation_data: MarkerSegmentationConfig | None = None
    ) -> None:
        """Add a segmentation row to the dialog.

        Parameters
        ----------
        segmentation_data : MarkerSegmentationConfig or None
            Segmentation configuration data.
        """
        if isinstance(segmentation_data, bool):
            segmentation_data = None
        if not isinstance(segmentation_data, MarkerSegmentationConfig):
            segmentation_data = MarkerSegmentationConfig()
            self._segmentations.append(segmentation_data)
        row = MarkerSegmentationRow(self, segmentation_data)
        self._segmentation_rows.append(row)
        self._segmentations_layout.addWidget(row)
        self._renumber_segmentations()
        self._schedule_layout_update()

    def _remove_segmentation(self, row: "MarkerSegmentationRow") -> None:
        """Remove a segmentation row and its stored data.

        Parameters
        ----------
        row : MarkerSegmentationRow
            Row instance to remove.
        """
        if row not in self._segmentation_rows:
            return
        self._segmentation_rows.remove(row)
        if row.data in self._segmentations:
            self._segmentations.remove(row.data)
        self._segmentations_layout.removeWidget(row)
        row.deleteLater()
        self._renumber_segmentations()
        self._schedule_layout_update()

    def _renumber_segmentations(self) -> None:
        """Update segmentation row titles after changes."""
        for index, row in enumerate(self._segmentation_rows, start=1):
            row.update_title(index)

    def _start_layout_watch(self) -> None:
        """Start a timer to monitor layout changes in the dialog."""
        if self._layout_watch_timer is not None:
            return
        self._layout_watch_timer = QTimer(self)
        self._layout_watch_timer.setInterval(150)
        self._layout_watch_timer.timeout.connect(self._poll_layout)
        self._layout_watch_timer.start()

    def _schedule_layout_update(self) -> None:
        """Schedule a layout update on the next timer tick."""
        self._layout_last_sizes.clear()

    def _poll_layout(self) -> None:
        """Recompute layout sizing when content changes."""
        self._apply_scroll_area_layout(
            "segmentations",
            self._segmentations_scroll_area,
            self._segmentations_layout,
            max_ratio=0.25,
        )
        self._apply_scroll_area_layout(
            "channels",
            self._channels_scroll_area,
            self._channels_layout,
            max_ratio=0.45,
        )

    def _apply_scroll_area_layout(
        self,
        key: str,
        scroll_area: QScrollArea,
        layout: QVBoxLayout,
        max_ratio: float,
    ) -> None:
        """Apply sizing rules for a scroll area section.

        Parameters
        ----------
        key : str
            Cache key for the section size.
        scroll_area : QScrollArea
            Scroll area to resize.
        layout : QVBoxLayout
            Layout containing section rows.
        max_ratio : float
            Maximum height ratio relative to the screen.
        """
        size = self._layout_content_size(layout)
        if self._layout_last_sizes.get(key) == size:
            return
        self._layout_last_sizes[key] = size
        content_width, content_height = size
        screen = self.window().screen() if self.window() is not None else None
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        screen_height = screen.availableGeometry().height() if screen else 720
        target_height = max(180, int(screen_height * max_ratio))
        frame = scroll_area.frameWidth() * 2
        height = max(0, min(target_height, content_height + frame))
        scroll_area.setUpdatesEnabled(False)
        scroll_area.setFixedHeight(height)
        scroll_area.setUpdatesEnabled(True)
        scroll_area.updateGeometry()
        bar = scroll_area.verticalScrollBar()
        if bar.maximum() > 0:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        else:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            bar.setRange(0, 0)
            bar.setValue(0)

    def _layout_content_size(self, layout: QVBoxLayout) -> tuple[int, int]:
        """Return content size for a vertical layout.

        Parameters
        ----------
        layout : QVBoxLayout
            Layout to measure.

        Returns
        -------
        tuple of int
            (width, height) of the layout contents.
        """
        layout.activate()
        margins = layout.contentsMargins()
        spacing = layout.spacing()
        count = layout.count()
        total_height = margins.top() + margins.bottom()
        max_width = 0
        for index in range(count):
            item = layout.itemAt(index)
            widget = item.widget()
            if widget is None:
                item_size = item.sizeHint()
            else:
                widget.adjustSize()
                item_size = widget.sizeHint().expandedTo(
                    widget.minimumSizeHint()
                )
            max_width = max(max_width, item_size.width())
            total_height += item_size.height()
        if count > 1:
            total_height += spacing * (count - 1)
        total_width = margins.left() + margins.right() + max_width
        return (total_width, total_height)


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

    def _open_channels_dialog(self) -> None:
        """Open the channels configuration dialog."""
        dialog = self._ui.get("channels_dialog")
        if dialog is None or not isinstance(dialog, QDialog):
            dialog = MarkerChannelsDialog(self)
            self._ui["channels_dialog"] = dialog
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
