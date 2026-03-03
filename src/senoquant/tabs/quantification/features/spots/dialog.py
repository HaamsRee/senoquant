"""Spots channels dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config import (
    SpotsChannelConfig,
    SpotsFeatureData,
    SpotsSegmentationConfig,
)
from ..channel_autopopulate import (
    channel_label_from_layer,
    layer_identity,
    same_layer_identity,
    unique_channel_label,
)
from .rows import SpotsChannelRow, SpotsSegmentationRow

if TYPE_CHECKING:
    from .feature import SpotsFeature


class SpotsChannelsDialog(QDialog):
    """Dialog for configuring spots channels."""

    def __init__(self, feature: "SpotsFeature") -> None:
        """Initialize the spots channels dialog.

        Parameters
        ----------
        feature : SpotsFeature
            Spots feature instance owning the dialog.
        """
        super().__init__(feature._tab)
        self._feature = feature
        self._tab = feature._tab
        data = feature._state.data
        if not isinstance(data, SpotsFeatureData):
            data = SpotsFeatureData()
            feature._state.data = data
        self._data = data
        self._segmentations = data.segmentations
        self._channels = data.channels
        self._rows: list[SpotsChannelRow] = []
        self._segmentation_rows: list[SpotsSegmentationRow] = []
        self._layout_watch_timer: QTimer | None = None
        self._layout_last_sizes: dict[str, tuple[int, int]] = {}

        self.setWindowTitle("Spots channels")
        self.setMinimumSize(600, 800)
        layout = QVBoxLayout()

        segmentations_section = self._build_segmentations_section()
        channels_section = self._build_channels_section()
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(segmentations_section)
        splitter.addWidget(channels_section)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        close_button = QPushButton("Save")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self.setLayout(layout)
        self._load_segmentations()
        self._load_channels()
        self._update_auto_populate_enabled()
        self._start_layout_watch()

    def closeEvent(self, event) -> None:
        """Handle window close as a save action.

        Parameters
        ----------
        event : QCloseEvent
            Close event from Qt.
        """
        self.accept()
        event.accept()

    def _build_segmentations_section(self) -> QGroupBox:
        """Create the segmentations section with add/remove controls.

        Returns
        -------
        QGroupBox
            Group box containing segmentation rows and the add button.
        """
        section = QGroupBox(
            "Nuclear/cytoplasmic segmentations to exclude background spots"
        )
        section.setFlat(True)
        section.setStyleSheet(self._section_stylesheet())

        self._segmentations_container = QWidget()
        self._segmentations_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self._segmentations_layout = QVBoxLayout()
        self._segmentations_layout.setContentsMargins(0, 0, 0, 0)
        self._segmentations_layout.setSpacing(8)
        self._segmentations_container.setLayout(self._segmentations_layout)

        self._segmentations_scroll_area = QScrollArea()
        self._segmentations_scroll_area.setWidgetResizable(True)
        self._segmentations_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
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
        self._segmentations_section = section
        return section

    def _build_channels_section(self) -> QGroupBox:
        """Create the channels section with add/remove controls.

        Returns
        -------
        QGroupBox
            Group box containing channel rows and the add button.
        """
        self._channels_container = QWidget()
        self._channels_container.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self._channels_layout = QVBoxLayout()
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(8)
        self._channels_container.setLayout(self._channels_layout)

        section = QGroupBox("Channels")
        section.setFlat(True)
        section.setStyleSheet(self._section_stylesheet())

        self._channels_scroll_area = QScrollArea()
        self._channels_scroll_area.setWidgetResizable(True)
        self._channels_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self._channels_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._channels_scroll_area.setWidget(self._channels_container)

        add_button = QPushButton("Add channel")
        add_button.clicked.connect(self._add_channel)
        auto_populate_button = QPushButton("Auto populate channels")
        auto_populate_button.clicked.connect(self._auto_populate_channels)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(add_button, 3)
        controls_layout.addWidget(auto_populate_button, 1)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(10, 12, 10, 10)
        section_layout.addWidget(self._channels_scroll_area)
        section_layout.addLayout(controls_layout)
        section.setLayout(section_layout)

        self._channels_section = section
        self._auto_populate_button = auto_populate_button
        return section

    @staticmethod
    def _section_stylesheet() -> str:
        """Return the stylesheet used for dialog sections.

        Returns
        -------
        str
            Qt stylesheet string for section group boxes.
        """
        return (
            "QGroupBox {"
            "  margin-top: 8px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin;"
            "  subcontrol-position: top left;"
            "  padding: 0 6px;"
            "}"
        )

    def _refresh_labels_combo(self, combo: QComboBox, filter_type: str = "cellular") -> None:
        """Refresh labels layer options for the dialog.

        Parameters
        ----------
        combo : QComboBox
            Labels combo box to refresh.
        filter_type : str, optional
            Type of labels to show: "cellular" for nuc/cyto labels,
            "spots" for spot labels. Defaults to "cellular".
        """
        current = combo.currentText()
        combo.clear()
        viewer = self._tab._viewer
        if viewer is None:
            combo.addItem("Select labels")
            return
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Labels":
                # Filter based on label type
                if filter_type == "cellular" and self._is_cellular_label(layer):
                    combo.addItem(layer.name)
                elif filter_type == "spots" and self._is_spot_label(layer):
                    combo.addItem(layer.name)
        if current:
            index = combo.findText(current)
            if index != -1:
                combo.setCurrentIndex(index)

    def _layer_task(self, layer: object) -> str | None:
        """Return normalized segmentation task from layer metadata."""
        metadata = getattr(layer, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        task = metadata.get("task")
        if not isinstance(task, str):
            return None
        normalized = task.strip().lower()
        return normalized or None

    def _is_cellular_label(self, layer: object | str) -> bool:
        """Check if a label layer is a cellular segmentation.

        Parameters
        ----------
        layer : object or str
            Labels layer object or labels layer name.

        Returns
        -------
        bool
            True if the layer is a cellular label (nuclear or cytoplasmic).
        """
        if isinstance(layer, str):
            layer_name = layer
            task = None
        else:
            layer_name = str(getattr(layer, "name", ""))
            task = self._layer_task(layer)
        if task in {"nuclear", "cytoplasmic"}:
            return True
        if task is not None:
            return False
        return layer_name.endswith("_nuc_labels") or layer_name.endswith("_cyto_labels")

    def _is_spot_label(self, layer: object | str) -> bool:
        """Check if a label layer is a spot segmentation.

        Parameters
        ----------
        layer : object or str
            Labels layer object or labels layer name.

        Returns
        -------
        bool
            True if the layer is a spot label.
        """
        if isinstance(layer, str):
            layer_name = layer
            task = None
        else:
            layer_name = str(getattr(layer, "name", ""))
            task = self._layer_task(layer)
        if task == "spots":
            return True
        if task is not None:
            return False
        return layer_name.endswith("_spot_labels")

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

    def _image_layers(self) -> list[object]:
        """Return image layers currently available in the viewer."""
        viewer = self._tab._viewer
        if viewer is None:
            return []
        layers: list[object] = []
        for layer in viewer.layers:
            if layer.__class__.__name__ == "Image":
                layers.append(layer)
        return layers

    def _spot_label_layers(self) -> list[object]:
        """Return labels layers recognized as spot segmentations."""
        viewer = self._tab._viewer
        if viewer is None:
            return []
        layers: list[object] = []
        for layer in viewer.layers:
            if layer.__class__.__name__ != "Labels":
                continue
            if self._is_spot_label(layer):
                layers.append(layer)
        return layers

    def _channel_row_for_data(
        self, channel_data: SpotsChannelConfig
    ) -> SpotsChannelRow | None:
        """Return the UI row backing a channel config object."""
        for row in self._rows:
            if row.data is channel_data:
                return row
        return None

    def _suggest_channel_name(self, layer: object, used_names: set[str]) -> str:
        """Return a unique suggested channel label for the layer."""
        base_name = channel_label_from_layer(layer)
        suggested = unique_channel_label(base_name, used_names)
        used_names.add(suggested)
        return suggested

    def _preferred_spot_suffixes(self) -> list[str]:
        """Infer ``<suffix>`` from existing ``<channel>_<suffix>`` mappings."""
        suffixes: list[str] = []
        seen: set[str] = set()
        for channel in self._channels:
            if not isinstance(channel, SpotsChannelConfig):
                continue
            channel_name = str(channel.channel).strip()
            spots_name = str(channel.spots_segmentation).strip()
            if not channel_name or not spots_name:
                continue
            prefix = f"{channel_name}_"
            if not spots_name.startswith(prefix):
                continue
            suffix = spots_name[len(prefix) :].strip()
            if not suffix or suffix in seen:
                continue
            seen.add(suffix)
            suffixes.append(suffix)
        return suffixes

    def _match_spots_layer(
        self,
        image_layer: object,
        *,
        spot_layers: list[object],
        used_spot_names: set[str],
        preferred_suffixes: list[str],
    ) -> object | None:
        """Return the best matching spots labels layer for an image layer."""
        image_name = str(getattr(image_layer, "name", "")).strip()
        if not image_name:
            return None

        available: list[object] = []
        available_by_name: dict[str, object] = {}
        for layer in spot_layers:
            layer_name = str(getattr(layer, "name", "")).strip()
            if not layer_name or layer_name in used_spot_names:
                continue
            available.append(layer)
            available_by_name[layer_name] = layer

        if not available:
            return None

        for suffix in preferred_suffixes:
            expected_name = f"{image_name}_{suffix}"
            expected_layer = available_by_name.get(expected_name)
            if expected_layer is not None:
                return expected_layer

        image_key = layer_identity(image_layer)
        identity_matches = [
            layer for layer in available if same_layer_identity(image_key, layer_identity(layer))
        ]
        if len(identity_matches) == 1:
            return identity_matches[0]

        prefix = f"{image_name}_"
        prefix_matches = [
            layer
            for layer in available
            if str(getattr(layer, "name", "")).startswith(prefix)
        ]
        if len(prefix_matches) == 1:
            return prefix_matches[0]

        return None

    def _update_auto_populate_enabled(self) -> None:
        """Enable auto-populate when channel/segmentation configuration exists."""
        button = getattr(self, "_auto_populate_button", None)
        if button is None:
            return
        has_channel_config = any(
            isinstance(channel, SpotsChannelConfig)
            and str(channel.channel).strip()
            for channel in self._channels
        )
        has_segmentation_config = any(
            isinstance(segmentation, SpotsSegmentationConfig)
            and str(segmentation.label).strip()
            for segmentation in self._segmentations
        )
        button.setEnabled(has_channel_config or has_segmentation_config)

    def _auto_populate_channels(self) -> None:
        """Auto-create channel rows and resolve spot segmentation matches."""
        image_layers = self._image_layers()
        if not image_layers:
            return
        spot_layers = self._spot_label_layers()

        ordered_image_names: list[str] = []
        image_by_name: dict[str, object] = {}
        for layer in image_layers:
            layer_name = str(getattr(layer, "name", "")).strip()
            if not layer_name or layer_name in image_by_name:
                continue
            ordered_image_names.append(layer_name)
            image_by_name[layer_name] = layer
        used_names: set[str] = {
            str(channel.name).strip()
            for channel in self._channels
            if isinstance(channel, SpotsChannelConfig) and str(channel.name).strip()
        }
        used_spot_names: set[str] = {
            str(channel.spots_segmentation).strip()
            for channel in self._channels
            if isinstance(channel, SpotsChannelConfig)
            and str(channel.spots_segmentation).strip()
        }
        configured_channels = {
            str(channel.channel).strip()
            for channel in self._channels
            if isinstance(channel, SpotsChannelConfig)
            and str(channel.channel).strip()
        }
        available_image_names = [
            image_name
            for image_name in ordered_image_names
            if image_name not in configured_channels
        ]
        preferred_suffixes = self._preferred_spot_suffixes()

        for channel_data in self._channels:
            if not isinstance(channel_data, SpotsChannelConfig):
                continue
            row = self._channel_row_for_data(channel_data)
            channel_name = str(channel_data.channel).strip()
            if not channel_name and available_image_names:
                channel_name = available_image_names.pop(0)
                if row is None:
                    channel_data.channel = channel_name
                else:
                    self._refresh_image_combo(row._channel_combo)
                    row._channel_combo.setCurrentText(channel_name)
                configured_channels.add(channel_name)
            if not channel_name:
                continue
            image_layer = image_by_name.get(channel_name)
            if image_layer is None:
                continue

            if not str(channel_data.name).strip():
                suggested_name = self._suggest_channel_name(image_layer, used_names)
                if row is None:
                    channel_data.name = suggested_name
                else:
                    row._name_input.setText(suggested_name)

            if str(channel_data.spots_segmentation).strip():
                continue
            matched_spot_layer = self._match_spots_layer(
                image_layer,
                spot_layers=spot_layers,
                used_spot_names=used_spot_names,
                preferred_suffixes=preferred_suffixes,
            )
            if matched_spot_layer is None:
                continue
            spot_name = str(getattr(matched_spot_layer, "name", "")).strip()
            if not spot_name:
                continue
            used_spot_names.add(spot_name)
            if row is None:
                channel_data.spots_segmentation = spot_name
            else:
                self._refresh_labels_combo(row._segmentation_combo, filter_type="spots")
                row._segmentation_combo.setCurrentText(spot_name)

        for image_name in available_image_names:
            image_layer = image_by_name.get(image_name)
            if image_layer is None:
                continue
            suggested_name = self._suggest_channel_name(image_layer, used_names)
            spot_name = ""
            matched_spot_layer = self._match_spots_layer(
                image_layer,
                spot_layers=spot_layers,
                used_spot_names=used_spot_names,
                preferred_suffixes=preferred_suffixes,
            )
            if matched_spot_layer is not None:
                spot_name = str(getattr(matched_spot_layer, "name", "")).strip()
            self._add_channel(
                SpotsChannelConfig(
                    name=suggested_name,
                    channel=image_name,
                    spots_segmentation=spot_name,
                )
            )
            configured_channels.add(image_name)
            if spot_name:
                used_spot_names.add(spot_name)

        self._update_auto_populate_enabled()

    def _load_segmentations(self) -> None:
        """Build segmentation rows from stored data."""
        if not self._segmentations:
            return
        for segmentation_data in self._segmentations:
            if not isinstance(segmentation_data, SpotsSegmentationConfig):
                continue
            self._add_segmentation(segmentation_data)

    def _load_channels(self) -> None:
        """Build channel rows from stored data."""
        if not self._channels:
            return
        for channel_data in self._channels:
            if not isinstance(channel_data, SpotsChannelConfig):
                continue
            self._add_channel(channel_data)

    def _add_channel(self, channel_data: SpotsChannelConfig | None = None) -> None:
        """Add a channel row to the dialog.

        Parameters
        ----------
        channel_data : SpotsChannelConfig or None
            Channel configuration data.
        """
        if isinstance(channel_data, bool):
            channel_data = None
        if not isinstance(channel_data, SpotsChannelConfig):
            channel_data = SpotsChannelConfig()
        if channel_data not in self._channels:
            self._channels.append(channel_data)
        initial_channel_name = str(channel_data.channel).strip()
        initial_spots_name = str(channel_data.spots_segmentation).strip()
        row = SpotsChannelRow(self, channel_data)
        self._rows.append(row)
        self._channels_layout.addWidget(row)
        if initial_channel_name and not str(channel_data.channel).strip():
            channel_data.channel = initial_channel_name
        if initial_channel_name:
            self._refresh_image_combo(row._channel_combo)
            row._channel_combo.setCurrentText(initial_channel_name)
        if initial_spots_name and not str(channel_data.spots_segmentation).strip():
            channel_data.spots_segmentation = initial_spots_name
        if initial_spots_name:
            self._refresh_labels_combo(row._segmentation_combo, filter_type="spots")
            row._segmentation_combo.setCurrentText(initial_spots_name)
        self._renumber_rows()
        self._update_auto_populate_enabled()
        self._schedule_layout_update()

    def _remove_channel(self, row: SpotsChannelRow) -> None:
        """Remove a channel row and its stored data.

        Parameters
        ----------
        row : SpotsChannelRow
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
        self._update_auto_populate_enabled()
        self._schedule_layout_update()

    def _renumber_rows(self) -> None:
        """Update channel row titles after changes."""
        for index, row in enumerate(self._rows, start=0):
            row.update_title(index)

    def _add_segmentation(
        self, segmentation_data: SpotsSegmentationConfig | None = None
    ) -> None:
        """Add a segmentation row to the dialog.

        Parameters
        ----------
        segmentation_data : SpotsSegmentationConfig or None
            Segmentation configuration data.
        """
        if isinstance(segmentation_data, bool):
            segmentation_data = None
        if not isinstance(segmentation_data, SpotsSegmentationConfig):
            segmentation_data = SpotsSegmentationConfig()
        if segmentation_data not in self._segmentations:
            self._segmentations.append(segmentation_data)
        initial_label_name = str(segmentation_data.label).strip()
        row = SpotsSegmentationRow(self, segmentation_data)
        self._segmentation_rows.append(row)
        self._segmentations_layout.addWidget(row)
        if initial_label_name and not str(segmentation_data.label).strip():
            segmentation_data.label = initial_label_name
        if initial_label_name:
            self._refresh_labels_combo(row._labels_combo, filter_type="cellular")
            row._labels_combo.setCurrentText(initial_label_name)
        self._renumber_segmentations()
        self._update_auto_populate_enabled()
        self._schedule_layout_update()

    def _remove_segmentation(self, row: SpotsSegmentationRow) -> None:
        """Remove a segmentation row and its stored data.

        Parameters
        ----------
        row : SpotsSegmentationRow
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
        self._update_auto_populate_enabled()
        self._schedule_layout_update()

    def _renumber_segmentations(self) -> None:
        """Update segmentation row titles after changes."""
        for index, row in enumerate(self._segmentation_rows, start=0):
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
            max_ratio=0.2,
        )
        self._apply_scroll_area_layout(
            "channels",
            self._channels_scroll_area,
            self._channels_layout,
            max_ratio=0.8,
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
        content = scroll_area.widget()
        if content is not None:
            content.setMinimumWidth(scroll_area.viewport().width())
        scroll_area.updateGeometry()
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

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
                item_size = widget.sizeHint().expandedTo(
                    widget.minimumSizeHint()
                )
            max_width = max(max_width, item_size.width())
            total_height += item_size.height()
        if count > 1:
            total_height += spacing * (count - 1)
        total_width = margins.left() + margins.right() + max_width
        return (total_width, total_height)
