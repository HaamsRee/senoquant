"""Frontend widget for the Batch tab.

This module defines the Qt UI for configuring and running batch processing.
The UI builds a :class:`BatchJobConfig`, then delegates execution to the
batch backend in a background thread.
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    show_console_notification = None
    Notification = None
    NotificationSeverity = None

from .backend import BatchBackend
from .config import (
    BatchChannelConfig,
    BatchCytoplasmicConfig,
    BatchJobConfig,
    BatchQuantificationConfig,
    BatchSegmentationConfig,
    BatchSpotsConfig,
)
from .layers import BatchViewer, Image, Labels
from ..quantification.frontend import QuantificationTab
from ..segmentation.backend import SegmentationBackend
from ..spots.backend import SpotsBackend


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        """Initialize the combo box.

        Parameters
        ----------
        refresh_callback : callable or None, optional
            Callable invoked before the popup opens.
        parent : QWidget or None, optional
            Parent widget.
        """
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        """Invoke the refresh callback before showing the popup."""
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


class BatchTab(QWidget):
    """Batch processing tab for running segmentation and spot detection."""

    def __init__(
        self,
        backend: BatchBackend | None = None,
        napari_viewer=None,
    ) -> None:
        """Initialize the Batch tab UI.

        Parameters
        ----------
        backend : BatchBackend or None, optional
            Backend instance used to execute batch runs.
        napari_viewer : object or None, optional
            Napari viewer instance for populating layer choices.
        """
        super().__init__()
        self._viewer = napari_viewer
        self._segmentation_backend = SegmentationBackend()
        self._spots_backend = SpotsBackend()
        self._backend = backend or BatchBackend(
            segmentation_backend=self._segmentation_backend,
            spots_backend=self._spots_backend,
        )
        self._active_workers: list[tuple[QThread, QObject]] = []
        self._channel_rows: list[dict] = []
        self._channel_configs: list[BatchChannelConfig] = []
        self._spot_channel_rows: list[dict] = []
        self._nuclear_settings_widgets: dict[str, object] = {}
        self._nuclear_settings_meta: dict[str, dict] = {}
        self._nuclear_settings_values: dict[str, object] = {}
        self._nuclear_settings_list: list[dict] = []
        self._cyto_settings_widgets: dict[str, object] = {}
        self._cyto_settings_meta: dict[str, dict] = {}
        self._cyto_settings_values: dict[str, object] = {}
        self._cyto_settings_list: list[dict] = []
        self._spot_settings_widgets: dict[str, object] = {}
        self._spot_settings_meta: dict[str, dict] = {}
        self._spot_settings_values: dict[str, object] = {}
        self._spot_settings_list: list[dict] = []
        self._spot_min_size_spin: QSpinBox | None = None
        self._spot_max_size_spin: QSpinBox | None = None
        self._add_spot_button: QPushButton | None = None
        self._config_viewer = BatchViewer()

        layout = QVBoxLayout()
        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.addWidget(self._make_input_section())
        content_layout.addWidget(self._make_channel_section())
        content_layout.addWidget(self._make_segmentation_section())
        content_layout.addWidget(self._make_spots_section())
        content_layout.addWidget(self._make_quantification_section())
        content_layout.addWidget(self._make_output_section())
        content_layout.addStretch(1)
        content.setLayout(content_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self._scroll_area = scroll
        self._apply_scroll_height()
        layout.addWidget(scroll)

        self._run_button = QPushButton("Run batch")
        self._run_button.clicked.connect(self._run_batch)
        layout.addWidget(self._run_button)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("Ready")
        self._status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_segmentation_models()
        self._refresh_cyto_models()
        self._refresh_detectors()
        self._refresh_channel_choices()
        self._refresh_spot_channel_choices()
        self._update_processing_state()

    def showEvent(self, event) -> None:
        """Re-apply scroll sizing when the widget is shown."""
        super().showEvent(event)
        self._apply_scroll_height()

    def resizeEvent(self, event) -> None:
        """Re-apply scroll sizing when the widget is resized."""
        super().resizeEvent(event)
        self._apply_scroll_height()

    def _make_input_section(self) -> QGroupBox:
        """Build the input configuration section."""
        section = QGroupBox("Input")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._input_path = QLineEdit()
        self._input_path.setPlaceholderText("Folder with images")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_input_path)
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.addWidget(self._input_path)
        input_row.addWidget(browse_button)
        input_widget = QWidget()
        input_widget.setLayout(input_row)

        self._extensions = QLineEdit()
        self._extensions.setPlaceholderText(".tif,.tiff,.ome.tif,.png,.jpg")
        self._extensions.setText(
            ".tif,.tiff,.ome.tif,.ome.tiff,.png,.jpg,.jpeg,.czi,.nd2,.lif,.zarr"
        )

        self._include_subfolders = QCheckBox("Include subfolders")
        self._process_scenes = QCheckBox("Process all scenes")

        profile_row = QHBoxLayout()
        profile_row.setContentsMargins(0, 0, 0, 0)
        load_button = QPushButton("Load profile")
        load_button.clicked.connect(self._load_profile)
        save_button = QPushButton("Save profile")
        save_button.clicked.connect(self._save_profile)
        profile_row.addWidget(load_button)
        profile_row.addWidget(save_button)
        profile_widget = QWidget()
        profile_widget.setLayout(profile_row)

        form_layout.addRow("Input folder", input_widget)
        form_layout.addRow("Extensions", self._extensions)
        form_layout.addRow("", self._include_subfolders)
        form_layout.addRow("", self._process_scenes)
        form_layout.addRow("Profiles", profile_widget)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _apply_scroll_height(self) -> None:
        """Pin scroll area height to 75% of the parent widget."""
        parent = self.parentWidget()
        if parent is None:
            return
        height = int(parent.height() * 0.75)
        if hasattr(self, "_scroll_area") and self._scroll_area is not None:
            self._scroll_area.setMinimumHeight(height)
            self._scroll_area.setMaximumHeight(height)

    def _make_channel_section(self) -> QGroupBox:
        """Build the channel mapping section."""
        section = QGroupBox("Channels")
        section_layout = QVBoxLayout()

        self._channels_container = QWidget()
        self._channels_layout = QVBoxLayout()
        self._channels_layout.setContentsMargins(0, 0, 0, 0)
        self._channels_layout.setSpacing(6)
        self._channels_container.setLayout(self._channels_layout)

        add_button = QPushButton("Add channel")
        add_button.clicked.connect(self._add_channel_row)

        section_layout.addWidget(self._channels_container)
        section_layout.addWidget(add_button)
        section.setLayout(section_layout)

        if not self._channel_rows:
            self._add_channel_row()
        return section

    def _make_segmentation_section(self) -> QGroupBox:
        """Build the segmentation configuration section."""
        section = QGroupBox("Segmentation")
        section_layout = QVBoxLayout()

        nuclear_layout = QFormLayout()
        nuclear_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._nuclear_enabled = QCheckBox("Run nuclear segmentation")
        self._nuclear_enabled.setChecked(True)
        self._nuclear_enabled.toggled.connect(self._update_processing_state)
        self._nuclear_model_combo = RefreshingComboBox(
            refresh_callback=self._refresh_segmentation_models
        )
        self._nuclear_channel_combo = QComboBox()
        nuclear_layout.addRow(self._nuclear_enabled)
        nuclear_layout.addRow("Nuclear model", self._nuclear_model_combo)
        nuclear_layout.addRow("Nuclear channel", self._nuclear_channel_combo)

        self._nuclear_settings_button = QPushButton("Edit nuclear settings")
        self._nuclear_settings_button.clicked.connect(
            lambda: self._open_settings_dialog("nuclear")
        )

        self._nuclear_model_combo.currentTextChanged.connect(
            lambda _text: self._update_nuclear_settings()
        )

        cyto_layout = QFormLayout()
        cyto_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._cyto_enabled = QCheckBox("Run cytoplasmic segmentation")
        self._cyto_enabled.setChecked(False)
        self._cyto_enabled.toggled.connect(self._update_processing_state)
        self._cyto_model_combo = RefreshingComboBox(
            refresh_callback=self._refresh_cyto_models
        )
        self._cyto_channel_combo = QComboBox()
        self._cyto_nuclear_combo = QComboBox()
        self._cyto_nuclear_label = QLabel("Nuclear channel")
        self._cyto_nuclear_optional = False
        cyto_layout.addRow(self._cyto_enabled)
        cyto_layout.addRow("Cytoplasmic model", self._cyto_model_combo)
        cyto_layout.addRow("Cytoplasmic channel", self._cyto_channel_combo)
        cyto_layout.addRow(self._cyto_nuclear_label, self._cyto_nuclear_combo)

        self._cyto_settings_button = QPushButton("Edit cytoplasmic settings")
        self._cyto_settings_button.clicked.connect(
            lambda: self._open_settings_dialog("cyto")
        )

        self._cyto_model_combo.currentTextChanged.connect(
            lambda _text: self._update_cyto_settings()
        )

        section_layout.addLayout(nuclear_layout)
        section_layout.addWidget(self._nuclear_settings_button)
        section_layout.addLayout(cyto_layout)
        section_layout.addWidget(self._cyto_settings_button)
        section.setLayout(section_layout)
        return section

    def _make_spots_section(self) -> QGroupBox:
        """Build the spot detection configuration section."""
        section = QGroupBox("Spot detection")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._spots_enabled = QCheckBox("Run spot detection")
        self._spots_enabled.setChecked(True)
        self._spots_enabled.toggled.connect(self._update_processing_state)
        self._spot_detector_combo = RefreshingComboBox(
            refresh_callback=self._refresh_detectors
        )

        form_layout.addRow(self._spots_enabled)
        form_layout.addRow("Spot detector", self._spot_detector_combo)
        self._spot_settings_button = QPushButton("Edit spot settings")
        self._spot_settings_button.clicked.connect(
            lambda: self._open_settings_dialog("spot")
        )

        self._spot_channels_container = QWidget()
        self._spot_channels_layout = QVBoxLayout()
        self._spot_channels_layout.setContentsMargins(0, 0, 0, 0)
        self._spot_channels_layout.setSpacing(6)
        self._spot_channels_container.setLayout(self._spot_channels_layout)
        self._add_spot_button = QPushButton("Add spot channel")
        self._add_spot_button.clicked.connect(self._add_spot_channel_row)

        self._spot_detector_combo.currentTextChanged.connect(
            lambda _text: self._update_spot_settings()
        )

        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._spot_settings_button)
        
        # Add size filter section
        size_filter_layout = QFormLayout()
        self._spot_min_size_spin = QSpinBox()
        self._spot_min_size_spin.setRange(0, 100000)
        self._spot_min_size_spin.setValue(0)
        
        self._spot_max_size_spin = QSpinBox()
        self._spot_max_size_spin.setRange(0, 100000)
        self._spot_max_size_spin.setValue(0)
        
        size_filter_layout.addRow("Minimum spot size (px)", self._spot_min_size_spin)
        size_filter_layout.addRow("Maximum spot size (px)", self._spot_max_size_spin)
        section_layout.addLayout(size_filter_layout)
        
        section_layout.addWidget(self._spot_channels_container)
        section_layout.addWidget(self._add_spot_button)
        section.setLayout(section_layout)
        self._refresh_spot_channel_choices()
        return section

    def _make_quantification_section(self) -> QGroupBox:
        """Build the quantification configuration section."""
        section = QGroupBox("Quantification")
        section_layout = QVBoxLayout()
        self._quant_enabled = QCheckBox("Run quantification")
        self._quant_enabled.setChecked(True)
        self._quant_enabled.toggled.connect(self._update_processing_state)
        self._quant_tab = QuantificationTab(
            napari_viewer=self._config_viewer,
            show_output_section=False,
            show_process_button=False,
            enable_rois=False,
            show_right_column=False,
            enable_thresholds=False,
        )
        section_layout.addWidget(self._quant_enabled)
        section_layout.addWidget(self._quant_tab)
        section.setLayout(section_layout)
        return section

    def _make_output_section(self) -> QGroupBox:
        """Build the output configuration section."""
        section = QGroupBox("Output")
        section_layout = QVBoxLayout()
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self._output_path = QLineEdit()
        self._output_path.setPlaceholderText("Output folder")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._select_output_path)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.addWidget(self._output_path)
        output_row.addWidget(browse_button)
        output_widget = QWidget()
        output_widget.setLayout(output_row)

        self._output_format = QComboBox()
        self._output_format.addItems(["tif", "npy"])

        self._quant_format = QComboBox()
        self._quant_format.addItems(["xlsx", "csv"])

        self._overwrite = QCheckBox("Overwrite existing outputs")

        form_layout.addRow("Output folder", output_widget)
        form_layout.addRow("Segmentation format", self._output_format)
        form_layout.addRow("Quantification format", self._quant_format)
        form_layout.addRow("", self._overwrite)

        section_layout.addLayout(form_layout)
        section.setLayout(section_layout)
        return section

    def _select_input_path(self) -> None:
        """Open a folder picker for the input path."""
        path = QFileDialog.getExistingDirectory(self, "Select input folder")
        if path:
            self._input_path.setText(path)

    def _select_output_path(self) -> None:
        """Open a folder picker for the output path."""
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self._output_path.setText(path)

    def _refresh_segmentation_models(self) -> None:
        """Refresh available nuclear segmentation models."""
        names = self._segmentation_backend.list_model_names(task="nuclear")
        self._nuclear_model_combo.clear()
        if names:
            self._nuclear_model_combo.addItems(names)
            self._nuclear_model_combo.setEnabled(True)
        else:
            self._nuclear_model_combo.addItem("(no models)")
            self._nuclear_model_combo.setEnabled(False)
        self._update_nuclear_settings()

    def _refresh_cyto_models(self) -> None:
        """Refresh available cytoplasmic segmentation models."""
        names = self._segmentation_backend.list_model_names(task="cytoplasmic")
        self._cyto_model_combo.clear()
        if names:
            self._cyto_model_combo.addItems(names)
            self._cyto_model_combo.setEnabled(True)
        else:
            self._cyto_model_combo.addItem("(no models)")
            self._cyto_model_combo.setEnabled(False)
        self._update_cyto_settings()

    def _refresh_detectors(self) -> None:
        """Refresh available spot detectors."""
        names = self._spots_backend.list_detector_names()
        self._spot_detector_combo.clear()
        if names:
            self._spot_detector_combo.addItems(names)
            self._spot_detector_combo.setEnabled(True)
        else:
            self._spot_detector_combo.addItem("(no detectors)")
            self._spot_detector_combo.setEnabled(False)
        self._update_spot_settings()

    def _add_spot_channel_row(self) -> None:
        """Add a new spot-channel row to the UI."""
        if not hasattr(self, "_spot_channels_layout"):
            return
        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        combo = QComboBox()
        delete_button = QPushButton("Delete")
        row_layout.addWidget(combo)
        row_layout.addWidget(delete_button)
        row_widget.setLayout(row_layout)

        row = {"widget": row_widget, "combo": combo, "delete_button": delete_button}
        self._spot_channel_rows.append(row)
        self._spot_channels_layout.addWidget(row_widget)

        delete_button.clicked.connect(lambda: self._remove_spot_channel_row(row))
        combo.currentTextChanged.connect(self._refresh_config_viewer)
        self._refresh_spot_channel_choices()

    def _remove_spot_channel_row(self, row: dict) -> None:
        """Remove a spot-channel row from the UI."""
        widget = row.get("widget")
        if widget is not None:
            widget.setParent(None)
        if row in self._spot_channel_rows:
            self._spot_channel_rows.remove(row)
        self._refresh_spot_channel_choices()

    def _refresh_spot_channel_choices(self) -> None:
        """Refresh spot-channel combo options based on channel map."""
        if not hasattr(self, "_spot_channels_layout"):
            return
        names = [config.name for config in self._channel_configs] or ["0"]
        for row in self._spot_channel_rows:
            combo = row["combo"]
            current = combo.currentText()
            combo.clear()
            combo.addItems(names)
            if current:
                index = combo.findText(current)
                if index != -1:
                    combo.setCurrentIndex(index)
        if not self._spot_channel_rows:
            self._add_spot_channel_row()
        self._refresh_config_viewer()

    def _add_channel_row(self, config: BatchChannelConfig | None = None) -> None:
        """Add a channel mapping row.

        Parameters
        ----------
        config : BatchChannelConfig or None, optional
            Pre-populated channel config. When None, a default row is created.
        """
        if isinstance(config, bool):
            config = None
        if config is None:
            config = BatchChannelConfig(name="", index=len(self._channel_rows))

        row_widget = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        name_input = QLineEdit()
        name_input.setPlaceholderText("Channel name")
        name_input.setText(config.name)
        index_input = QSpinBox()
        index_input.setMinimum(0)
        index_input.setMaximum(4096)
        index_input.setValue(config.index)
        delete_button = QPushButton("Delete")

        row_layout.addWidget(name_input)
        row_layout.addWidget(index_input)
        row_layout.addWidget(delete_button)
        row_widget.setLayout(row_layout)

        row = {
            "widget": row_widget,
            "name": name_input,
            "index": index_input,
        }
        self._channel_rows.append(row)
        self._channels_layout.addWidget(row_widget)

        name_input.textChanged.connect(self._sync_channel_map)
        index_input.valueChanged.connect(self._sync_channel_map)
        delete_button.clicked.connect(lambda: self._remove_channel_row(row))

        self._sync_channel_map()

    def _remove_channel_row(self, row: dict) -> None:
        """Remove a channel mapping row."""
        widget = row.get("widget")
        if widget is not None:
            widget.setParent(None)
        if row in self._channel_rows:
            self._channel_rows.remove(row)
        self._sync_channel_map()

    def _sync_channel_map(self) -> None:
        """Sync UI channel rows into BatchChannelConfig objects."""
        configs: list[BatchChannelConfig] = []
        for row in self._channel_rows:
            name = row["name"].text().strip()
            index = row["index"].value()
            if not name:
                name = f"{index}"
            configs.append(BatchChannelConfig(name=name, index=index))
        self._channel_configs = configs
        self._refresh_channel_choices()
        if hasattr(self, "_spot_channels_layout"):
            self._refresh_spot_channel_choices()
        self._refresh_config_viewer()

    def _refresh_channel_choices(self) -> None:
        """Refresh combo boxes that depend on channel mapping."""
        names = [config.name for config in self._channel_configs]

        def populate_combo(
            combo: QComboBox,
            *,
            include_none: bool = False,
            none_label: str = "(none)",
        ) -> None:
            current = combo.currentText()
            combo.clear()
            items: list[str] = []
            if include_none:
                items.append(none_label)
            if names:
                items.extend(names)
            elif not include_none:
                items.append("0")
            if not items:
                items.append(none_label)
            combo.addItems(items)
            if current:
                index = combo.findText(current)
                if index != -1:
                    combo.setCurrentIndex(index)

        if getattr(self, "_nuclear_channel_combo", None) is not None:
            populate_combo(self._nuclear_channel_combo)
        if getattr(self, "_cyto_channel_combo", None) is not None:
            populate_combo(self._cyto_channel_combo)
        if getattr(self, "_cyto_nuclear_combo", None) is not None:
            populate_combo(
                self._cyto_nuclear_combo,
                include_none=self._cyto_nuclear_optional,
            )

    def _refresh_config_viewer(self) -> None:
        """Refresh the quantification preview viewer shim."""
        layers: list[object] = []
        for config in self._channel_configs:
            # Add placeholder image layers so quantification UI can list names.
            layers.append(Image(None, config.name))
        if getattr(self, "_nuclear_enabled", None) is not None and self._nuclear_enabled.isChecked():
            nuclear_model = self._nuclear_model_combo.currentText()
            nuclear_channel = self._nuclear_channel_combo.currentText()
            if nuclear_model and nuclear_channel and not nuclear_model.startswith("("):
                label_name = f"{nuclear_channel}_{nuclear_model}_nuc_labels"
                layers.append(Labels(None, label_name))
        if getattr(self, "_cyto_enabled", None) is not None and self._cyto_enabled.isChecked():
            cyto_model = self._cyto_model_combo.currentText()
            cyto_channel = self._cyto_channel_combo.currentText()
            if cyto_model and cyto_channel and not cyto_model.startswith("("):
                label_name = f"{cyto_channel}_{cyto_model}_cyto_labels"
                layers.append(Labels(None, label_name))
        if getattr(self, "_spots_enabled", None) is not None and self._spots_enabled.isChecked():
            spot_detector = self._spot_detector_combo.currentText()
            if spot_detector and not spot_detector.startswith("("):
                for label_name in _spot_label_names(self._spot_channel_rows, spot_detector):
                    layers.append(Labels(None, label_name))
        self._config_viewer.set_layers(layers)

    def _update_nuclear_settings(self) -> None:
        """Refresh nuclear model settings from the selected model."""
        model_name = self._nuclear_model_combo.currentText()
        self._nuclear_settings_widgets.clear()
        self._nuclear_settings_meta.clear()
        if not model_name or model_name.startswith("("):
            return
        model = self._segmentation_backend.get_model(model_name)
        settings = model.list_settings()
        self._nuclear_settings_list = list(settings)
        self._nuclear_settings_meta = {
            item.get("key", item.get("label", "")): item for item in settings
        }
        self._nuclear_settings_values = _defaults_from_settings(settings)

    def _update_cyto_settings(self) -> None:
        """Refresh cytoplasmic model settings from the selected model."""
        model_name = self._cyto_model_combo.currentText()
        self._cyto_settings_widgets.clear()
        self._cyto_settings_meta.clear()
        if not model_name or model_name.startswith("("):
            self._cyto_nuclear_combo.setEnabled(False)
            if hasattr(self, "_cyto_nuclear_label"):
                self._cyto_nuclear_label.setText("Nuclear channel")
            self._cyto_nuclear_optional = False
            return
        model = self._segmentation_backend.get_model(model_name)
        settings = model.list_settings()
        self._cyto_settings_list = list(settings)
        self._cyto_settings_meta = {
            item.get("key", item.get("label", "")): item for item in settings
        }
        self._cyto_settings_values = _defaults_from_settings(settings)
        modes = model.cytoplasmic_input_modes()
        supports_nuclear = "nuclear+cytoplasmic" in modes
        if supports_nuclear:
            optional = model.cytoplasmic_nuclear_optional()
            suffix = "optional" if optional else "required"
            if hasattr(self, "_cyto_nuclear_label"):
                self._cyto_nuclear_label.setText(f"Nuclear channel ({suffix})")
            self._cyto_nuclear_combo.setEnabled(True)
            self._cyto_nuclear_optional = optional
        else:
            if hasattr(self, "_cyto_nuclear_label"):
                self._cyto_nuclear_label.setText("Nuclear channel")
            self._cyto_nuclear_combo.setEnabled(False)
            self._cyto_nuclear_optional = False
        self._refresh_channel_choices()

    def _update_spot_settings(self) -> None:
        """Refresh spot detector settings from the selected detector."""
        detector_name = self._spot_detector_combo.currentText()
        self._spot_settings_widgets.clear()
        self._spot_settings_meta.clear()
        if not detector_name or detector_name.startswith("("):
            return
        detector = self._spots_backend.get_detector(detector_name)
        settings = detector.list_settings()
        self._spot_settings_list = list(settings)
        self._spot_settings_meta = {
            item.get("key", item.get("label", "")): item for item in settings
        }
        self._spot_settings_values = _defaults_from_settings(settings)

    def _open_settings_dialog(self, kind: str) -> None:
        """Open a settings dialog for model/detector configuration.

        Parameters
        ----------
        kind : {"nuclear", "cyto", "spot"}
            Settings group to edit.
        """
        if kind == "nuclear":
            title = "Nuclear settings"
            settings = list(self._nuclear_settings_list)
            widgets = self._nuclear_settings_widgets
            values = self._nuclear_settings_values
            meta = self._nuclear_settings_meta
        elif kind == "cyto":
            title = "Cytoplasmic settings"
            settings = list(self._cyto_settings_list)
            widgets = self._cyto_settings_widgets
            values = self._cyto_settings_values
            meta = self._cyto_settings_meta
        else:
            title = "Spot settings"
            settings = list(self._spot_settings_list)
            widgets = self._spot_settings_widgets
            values = self._spot_settings_values
            meta = self._spot_settings_meta

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog_layout = QVBoxLayout()
        form_layout = QFormLayout()
        widgets.clear()
        for setting in settings:
            setting_type = setting.get("type")
            label = setting.get("label", setting.get("key", "Setting"))
            key = setting.get("key", label)
            default = setting.get("default", 0)
            if setting_type == "float":
                widget = QDoubleSpinBox()
                decimals = int(setting.get("decimals", 1))
                widget.setDecimals(decimals)
                widget.setRange(
                    float(setting.get("min", 0.0)),
                    float(setting.get("max", 1.0)),
                )
                widget.setSingleStep(0.1)
                widget.setValue(float(values.get(key, default)))
            elif setting_type == "int":
                widget = QSpinBox()
                widget.setRange(
                    int(setting.get("min", 0)),
                    int(setting.get("max", 100)),
                )
                widget.setSingleStep(1)
                widget.setValue(int(values.get(key, default)))
            elif setting_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(values.get(key, default)))
                widget.toggled.connect(
                    lambda _checked, m=widgets, meta_ref=meta: self._apply_setting_dependencies(m, meta_ref)
                )
            else:
                widget = QLabel("Unsupported setting type")
            widgets[key] = widget
            form_layout.addRow(label, widget)
        dialog_layout.addLayout(form_layout)
        self._apply_setting_dependencies(widgets, meta)
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button)
        dialog.setLayout(dialog_layout)
        dialog.exec()
        values.update(self._collect_settings(widgets))

    def _apply_setting_dependencies(self, settings_widgets: dict, settings_meta: dict) -> None:
        """Enable/disable settings based on dependency metadata."""
        for key, setting in settings_meta.items():
            widget = settings_widgets.get(key)
            if widget is None:
                continue
            enabled_by = setting.get("enabled_by")
            disabled_by = setting.get("disabled_by")
            if enabled_by:
                controller = settings_widgets.get(enabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(controller.isChecked())
            if disabled_by:
                controller = settings_widgets.get(disabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(not controller.isChecked())

    @staticmethod
    def _collect_settings(settings_widgets: dict) -> dict:
        """Collect values from settings widgets into a dictionary."""
        values = {}
        for key, widget in settings_widgets.items():
            try:
                if hasattr(widget, "value"):
                    values[key] = widget.value()
                elif isinstance(widget, QCheckBox):
                    values[key] = widget.isChecked()
            except RuntimeError:
                # Widget was deleted; ignore stale references.
                continue
        return values

    def _update_processing_state(self) -> None:
        """Enable/disable UI sections based on checkbox states."""
        nuclear_enabled = self._nuclear_enabled.isChecked()
        cyto_enabled = self._cyto_enabled.isChecked()
        spot_enabled = self._spots_enabled.isChecked()
        self._nuclear_model_combo.setEnabled(nuclear_enabled)
        self._nuclear_channel_combo.setEnabled(nuclear_enabled)
        self._nuclear_settings_button.setEnabled(nuclear_enabled)
        self._cyto_model_combo.setEnabled(cyto_enabled)
        self._cyto_channel_combo.setEnabled(cyto_enabled)
        self._cyto_nuclear_combo.setEnabled(cyto_enabled)
        self._cyto_settings_button.setEnabled(cyto_enabled)
        self._spot_detector_combo.setEnabled(spot_enabled)
        self._spot_settings_button.setEnabled(spot_enabled)
        if self._spot_min_size_spin is not None:
            self._spot_min_size_spin.setEnabled(spot_enabled)
        if self._spot_max_size_spin is not None:
            self._spot_max_size_spin.setEnabled(spot_enabled)
        if self._add_spot_button is not None:
            self._add_spot_button.setEnabled(spot_enabled)
        for row in self._spot_channel_rows:
            combo = row.get("combo")
            if combo is not None:
                combo.setEnabled(spot_enabled)
            delete_button = row.get("delete_button")
            if delete_button is not None:
                delete_button.setEnabled(spot_enabled)
        self._quant_tab.setEnabled(self._quant_enabled.isChecked())

        self._refresh_config_viewer()

    def _run_batch(self) -> None:
        """Validate inputs and launch the batch job."""
        input_path = self._input_path.text().strip()
        if not input_path:
            self._notify("Select an input folder.")
            return
        if not Path(input_path).exists():
            self._notify("Input folder does not exist.")
            return

        output_path = self._output_path.text().strip()
        if not output_path:
            output_path = str(Path(input_path) / "batch-output")
            self._output_path.setText(output_path)

        nuclear_model = None
        if self._nuclear_enabled.isChecked() and self._nuclear_model_combo.isEnabled():
            nuclear_model = self._nuclear_model_combo.currentText().strip()
            if nuclear_model.startswith("("):
                nuclear_model = None

        spot_detector = None
        if self._spots_enabled.isChecked() and self._spot_detector_combo.isEnabled():
            spot_detector = self._spot_detector_combo.currentText().strip()
            if spot_detector.startswith("("):
                spot_detector = None

        cyto_model = None
        if self._cyto_enabled.isChecked() and self._cyto_model_combo.isEnabled():
            cyto_model = self._cyto_model_combo.currentText().strip()
            if cyto_model.startswith("("):
                cyto_model = None

        quant_features = (
            list(self._quant_tab._feature_configs)
            if self._quant_enabled.isChecked()
            else []
        )
        if (
            not nuclear_model
            and not cyto_model
            and not spot_detector
            and not quant_features
        ):
            self._notify("Enable segmentation, spots, or quantification.")
            return

        extensions = [
            ext.strip()
            for ext in self._extensions.text().split(",")
            if ext.strip()
        ]

        spot_channels = [
            row["combo"].currentText().strip()
            for row in self._spot_channel_rows
            if row.get("combo") is not None and row["combo"].currentText().strip()
        ]
        if self._spots_enabled.isChecked() and not spot_channels:
            self._notify("Select at least one spot channel.")
            return

        job = self._build_job_config()
        quant_contexts = (
            list(self._quant_tab._feature_configs)
            if self._quant_enabled.isChecked()
            else []
        )
        
        # Create a worker that can report progress
        worker = _RunWorker(lambda progress_cb: self._backend.process_folder(
            job.input_path,
            job.output_path,
            channel_map=job.channel_map,
            nuclear_model=job.nuclear.model if job.nuclear.enabled else None,
            nuclear_channel=job.nuclear.channel or None,
            nuclear_settings=job.nuclear.settings,
            cyto_model=job.cytoplasmic.model if job.cytoplasmic.enabled else None,
            cyto_channel=job.cytoplasmic.channel or None,
            cyto_nuclear_channel=job.cytoplasmic.nuclear_channel or None,
            cyto_settings=job.cytoplasmic.settings,
            spot_detector=job.spots.detector if job.spots.enabled else None,
            spot_channels=job.spots.channels,
            spot_settings=job.spots.settings,
            quantification_features=quant_contexts,
            quantification_format=job.quantification.format,
            quantification_tab=(
                self._quant_tab if self._quant_enabled.isChecked() else None
            ),
            extensions=job.extensions,
            include_subfolders=job.include_subfolders,
            output_format=job.output_format,
            overwrite=job.overwrite,
            process_all_scenes=job.process_all_scenes,
            progress_callback=progress_cb,
        ))
        
        self._start_background_run(
            run_button=self._run_button,
            run_text="Run batch",
            worker=worker,
            on_success=self._handle_batch_complete,
        )

    def _build_job_config(self) -> BatchJobConfig:
        """Build a BatchJobConfig from the current UI state."""
        nuclear_settings = self._collect_settings(self._nuclear_settings_widgets)
        if not nuclear_settings:
            nuclear_settings = self._nuclear_settings_values
        cyto_settings = self._collect_settings(self._cyto_settings_widgets)
        if not cyto_settings:
            cyto_settings = self._cyto_settings_values
        spot_settings = self._collect_settings(self._spot_settings_widgets)
        if not spot_settings:
            spot_settings = self._spot_settings_values
        spot_channels = [
            row["combo"].currentText().strip()
            for row in self._spot_channel_rows
            if row.get("combo") is not None and row["combo"].currentText().strip()
        ]
        quant_features = (
            [context.state for context in self._quant_tab._feature_configs]
            if self._quant_enabled.isChecked()
            else []
        )
        return BatchJobConfig(
            input_path=self._input_path.text().strip(),
            output_path=self._output_path.text().strip(),
            extensions=[
                ext.strip()
                for ext in self._extensions.text().split(",")
                if ext.strip()
            ],
            include_subfolders=self._include_subfolders.isChecked(),
            process_all_scenes=self._process_scenes.isChecked(),
            overwrite=self._overwrite.isChecked(),
            output_format=self._output_format.currentText(),
            channel_map=list(self._channel_configs),
            nuclear=BatchSegmentationConfig(
                enabled=self._nuclear_enabled.isChecked(),
                model=self._nuclear_model_combo.currentText(),
                channel=self._nuclear_channel_combo.currentText(),
                settings=nuclear_settings,
            ),
            cytoplasmic=BatchCytoplasmicConfig(
                enabled=self._cyto_enabled.isChecked(),
                model=self._cyto_model_combo.currentText(),
                channel=self._cyto_channel_combo.currentText(),
                nuclear_channel=(
                    ""
                    if self._cyto_nuclear_combo.currentText().strip() == "(none)"
                    else self._cyto_nuclear_combo.currentText()
                ),
                settings=cyto_settings,
            ),
            spots=BatchSpotsConfig(
                enabled=self._spots_enabled.isChecked(),
                detector=self._spot_detector_combo.currentText(),
                channels=spot_channels,
                settings=spot_settings,
                min_size=self._spot_min_size_spin.value() if self._spot_min_size_spin else 0,
                max_size=self._spot_max_size_spin.value() if self._spot_max_size_spin else 0,
            ),
            quantification=BatchQuantificationConfig(
                enabled=self._quant_enabled.isChecked(),
                format=self._quant_format.currentText(),
                features=quant_features,
            ),
        )

    def _apply_job_config(self, job: BatchJobConfig) -> None:
        """Populate the UI from a BatchJobConfig."""
        self._refresh_segmentation_models()
        self._refresh_cyto_models()
        self._refresh_detectors()
        self._input_path.setText(job.input_path)
        self._output_path.setText(job.output_path)
        self._extensions.setText(",".join(job.extensions))
        self._include_subfolders.setChecked(job.include_subfolders)
        self._process_scenes.setChecked(job.process_all_scenes)
        self._overwrite.setChecked(job.overwrite)
        self._output_format.setCurrentText(job.output_format)
        self._quant_format.setCurrentText(job.quantification.format)

        self._clear_channel_rows()
        for config in job.channel_map:
            self._add_channel_row(config)

        self._nuclear_enabled.setChecked(job.nuclear.enabled)
        self._set_combo_value(self._nuclear_model_combo, job.nuclear.model)
        self._set_combo_value(self._nuclear_channel_combo, job.nuclear.channel)
        self._nuclear_settings_values = dict(job.nuclear.settings)

        self._cyto_enabled.setChecked(job.cytoplasmic.enabled)
        self._set_combo_value(self._cyto_model_combo, job.cytoplasmic.model)
        self._set_combo_value(self._cyto_channel_combo, job.cytoplasmic.channel)
        if not job.cytoplasmic.nuclear_channel:
            if self._cyto_nuclear_combo.findText("(none)") != -1:
                self._set_combo_value(self._cyto_nuclear_combo, "(none)")
        else:
            self._set_combo_value(
                self._cyto_nuclear_combo, job.cytoplasmic.nuclear_channel
            )
        self._cyto_settings_values = dict(job.cytoplasmic.settings)

        self._spots_enabled.setChecked(job.spots.enabled)
        self._set_combo_value(self._spot_detector_combo, job.spots.detector)
        self._spot_settings_values = dict(job.spots.settings)
        if self._spot_min_size_spin is not None:
            self._spot_min_size_spin.setValue(job.spots.min_size)
        if self._spot_max_size_spin is not None:
            self._spot_max_size_spin.setValue(job.spots.max_size)
        self._clear_spot_channel_rows()
        for channel in job.spots.channels:
            self._add_spot_channel_row()
            if self._spot_channel_rows:
                self._set_combo_value(self._spot_channel_rows[-1]["combo"], channel)

        self._quant_enabled.setChecked(job.quantification.enabled)
        self._quant_tab.load_feature_configs(job.quantification.features)
        self._refresh_channel_choices()
        self._refresh_spot_channel_choices()
        self._refresh_config_viewer()

    def _save_profile(self) -> None:
        """Save the current configuration to a JSON profile."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save batch profile",
            str(Path.cwd() / "batch-profile.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        job = self._build_job_config()
        job.save(path)
        self._notify(f"Saved profile to {path}")

    def _load_profile(self) -> None:
        """Load a configuration from a JSON profile."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load batch profile",
            str(Path.cwd()),
            "JSON (*.json)",
        )
        if not path:
            return
        job = BatchJobConfig.load(path)
        self._apply_job_config(job)
        self._notify(f"Loaded profile from {path}")

    def _clear_channel_rows(self) -> None:
        """Remove all channel rows from the UI."""
        for row in list(self._channel_rows):
            widget = row.get("widget")
            if widget is not None:
                widget.setParent(None)
        self._channel_rows = []
        self._channel_configs = []

    def _clear_spot_channel_rows(self) -> None:
        """Remove all spot channel rows from the UI."""
        for row in list(self._spot_channel_rows):
            widget = row.get("widget")
            if widget is not None:
                widget.setParent(None)
        self._spot_channel_rows = []

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        """Set a combo box value if the item exists."""
        if not value:
            return
        index = combo.findText(value)
        if index != -1:
            combo.setCurrentIndex(index)

    def _start_background_run(
        self,
        *,
        run_button: QPushButton,
        run_text: str,
        worker: "_RunWorker",
        on_success,
    ) -> None:
        """Start a background thread to execute the batch job."""
        run_button.setEnabled(False)
        run_button.setText("Running...")
        self._status_label.setText("Running batch...")
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)

        thread = QThread()
        worker.moveToThread(thread)
        worker.progress.connect(self._update_progress)
        worker.finished.connect(lambda result: on_success(result))
        worker.finished.connect(
            lambda: self._finish_background_run(run_button, run_text, thread, worker)
        )
        worker.failed.connect(
            lambda message: self._notify(f"Batch run failed: {message}")
        )
        worker.failed.connect(
            lambda: self._finish_background_run(run_button, run_text, thread, worker)
        )
        thread.started.connect(worker.run)
        thread.start()
        self._active_workers.append((thread, worker))

    def _finish_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        thread: QThread,
        worker: QObject,
    ) -> None:
        """Restore UI state and clean up worker threads."""
        run_button.setEnabled(True)
        run_button.setText(run_text)
        self._status_label.setText("Ready")
        self._progress_bar.setVisible(False)
        self._progress_bar.setValue(0)
        thread.quit()
        thread.wait()
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass

    def _update_progress(self, current: int, total: int, message: str) -> None:
        """Update progress bar and status label."""
        if total > 0:
            percent = int((current / total) * 100)
            self._progress_bar.setValue(percent)
        self._status_label.setText(message)

    def _handle_batch_complete(self, summary) -> None:
        """Handle successful completion of a batch run."""
        message = (
            f"Batch complete: {summary.processed} processed, "
            f"{summary.failed} failed, {summary.skipped} skipped."
        )
        self._notify(message)

    def _notify(self, message: str) -> None:
        """Send a user-visible notification and update the status label."""
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )
        self._status_label.setText(message)


class _RunWorker(QObject):
    """Worker wrapper for background batch execution."""

    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)  # current, total, message

    def __init__(self, run_callable) -> None:
        """Initialize the worker.

        Parameters
        ----------
        run_callable : callable
            Callable invoked on the worker thread. Should accept a
            progress callback function as its argument.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute the job and emit result or error."""
        try:
            result = self._run_callable(self._emit_progress)
        except Exception as exc:  # pragma: no cover - runtime error path
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

    def _emit_progress(self, current: int, total: int, message: str) -> None:
        """Emit progress updates from the worker thread."""
        self.progress.emit(current, total, message)


def _defaults_from_settings(settings: list[dict]) -> dict[str, object]:
    """Extract default values from a list of model settings."""
    values: dict[str, object] = {}
    for setting in settings:
        key = setting.get("key") or setting.get("label") or "Setting"
        values[key] = setting.get("default", 0)
    return values


def _spot_label_names(rows: list[dict], detector_name: str = "") -> list[str]:
    """Build label layer names for spot channels."""
    labels: list[str] = []
    for row in rows:
        combo = row.get("combo")
        if combo is None:
            continue
        name = combo.currentText().strip()
        if not name:
            continue
        if detector_name:
            labels.append(f"{_sanitize_label(name)}_{detector_name}_spot_labels")
        else:
            labels.append(f"{_sanitize_label(name)}_spot_labels")
    return labels


def _sanitize_label(name: str) -> str:
    """Sanitize a label name for display and export."""
    safe = []
    for char in name.strip():
        if char.isalnum():
            safe.append(char)
        else:
            safe.append("_")
    result = "".join(safe).strip("_")
    return result or "spots"
