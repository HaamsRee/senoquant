"""Frontend widget for the Segmentation tab."""

from qtpy.QtCore import QObject, QThread, Signal
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QFrame,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.layers import Image, Labels
    from napari.utils.notifications import (
        Notification,
        NotificationSeverity,
        show_console_notification,
    )
except Exception:  # pragma: no cover - optional import for runtime
    Image = None
    Labels = None
    show_console_notification = None
    Notification = None
    NotificationSeverity = None


class RefreshingComboBox(QComboBox):
    """Combo box that refreshes its items when opened."""

    def __init__(self, refresh_callback=None, parent=None) -> None:
        """Create a combo box that refreshes on popup.

        Parameters
        ----------
        refresh_callback : callable or None
            Function invoked before showing the popup.
        parent : QWidget or None
            Optional parent widget.
        """
        super().__init__(parent)
        self._refresh_callback = refresh_callback

    def showPopup(self) -> None:
        """Refresh items before showing the popup."""
        if self._refresh_callback is not None:
            self._refresh_callback()
        super().showPopup()


# Layer dropdowns refresh at click-time so the UI stays in sync with napari.
# This keeps options limited to Image layers and preserves existing selections.

from .backend import SegmentationBackend
from ..settings.backend import SettingsBackend


class SegmentationTab(QWidget):
    """Segmentation tab UI with nuclear and cytoplasmic sections.

    Parameters
    ----------
    backend : SegmentationBackend or None
        Backend instance used to discover and load models.
    napari_viewer : object or None
        Napari viewer used to populate layer choices.
    settings_backend : SettingsBackend or None
        Settings store used for preload configuration.
    """

    def __init__(
        self,
        backend: SegmentationBackend | None = None,
        napari_viewer=None,
        settings_backend: SettingsBackend | None = None,
    ) -> None:
        """Create the segmentation tab UI.

        Parameters
        ----------
        backend : SegmentationBackend or None
            Backend instance used to discover and load models.
        napari_viewer : object or None
            Napari viewer used to populate layer choices.
        settings_backend : SettingsBackend or None
            Settings store used for preload configuration.
        """
        super().__init__()
        self._backend = backend or SegmentationBackend()
        self._viewer = napari_viewer
        self._nuclear_settings_widgets = {}
        self._cyto_settings_widgets = {}
        self._nuclear_settings_meta = {}
        self._cyto_settings_meta = {}
        self._settings = settings_backend or SettingsBackend()
        self._settings.preload_models_changed.connect(
            self._on_preload_models_changed
        )
        self._active_workers: list[tuple[QThread, QObject]] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_nuclear_section())
        layout.addWidget(self._make_cytoplasmic_section())
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_layer_choices()
        self._refresh_model_choices()
        self._update_nuclear_model_settings(self._nuclear_model_combo.currentText())
        self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())

        if self._settings.preload_models_enabled():
            if (
                show_console_notification is not None
                and Notification is not None
                and NotificationSeverity is not None
            ):
                show_console_notification(
                    Notification(
                        "Preloading segmentation models...",
                        severity=NotificationSeverity.INFO,
                    )
                )
            self._backend.preload_models()

    def _make_nuclear_section(self) -> QGroupBox:
        """Build the nuclear segmentation UI section.

        Returns
        -------
        QGroupBox
            Group box containing nuclear segmentation controls.
        """
        section = QGroupBox("Nuclear segmentation")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._nuclear_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._configure_combo(self._nuclear_layer_combo)
        self._nuclear_model_combo = QComboBox()
        self._configure_combo(self._nuclear_model_combo)
        self._nuclear_model_combo.currentTextChanged.connect(
            self._update_nuclear_model_settings
        )

        form_layout.addRow("Nuclear layer", self._nuclear_layer_combo)
        form_layout.addRow("Model", self._nuclear_model_combo)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(
            self._make_model_settings_section("Model settings", "nuclear")
        )

        self._nuclear_run_button = QPushButton("Run")
        self._nuclear_run_button.clicked.connect(self._run_nuclear)
        section_layout.addWidget(self._nuclear_run_button)
        section.setLayout(section_layout)

        return section

    def _make_cytoplasmic_section(self) -> QGroupBox:
        """Build the cytoplasmic segmentation UI section.

        Returns
        -------
        QGroupBox
            Group box containing cytoplasmic segmentation controls.
        """
        section = QGroupBox("Cytoplasmic segmentation")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._cyto_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._configure_combo(self._cyto_layer_combo)
        self._cyto_nuclear_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._configure_combo(self._cyto_nuclear_layer_combo)
        self._cyto_nuclear_layer_combo.currentTextChanged.connect(
            self._on_cyto_nuclear_layer_changed
        )
        self._cyto_model_combo = QComboBox()
        self._configure_combo(self._cyto_model_combo)
        self._cyto_model_combo.currentTextChanged.connect(
            self._update_cytoplasmic_model_settings
        )

        self._cyto_layer_label = QLabel("Cytoplasmic layer")
        form_layout.addRow(self._cyto_layer_label, self._cyto_layer_combo)
        self._cyto_nuclear_label = QLabel("Nuclear layer")
        form_layout.addRow(self._cyto_nuclear_label, self._cyto_nuclear_layer_combo)
        form_layout.addRow("Model", self._cyto_model_combo)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(
            self._make_model_settings_section("Model settings", "cytoplasmic")
        )

        self._cyto_run_button = QPushButton("Run")
        self._cyto_run_button.clicked.connect(self._run_cytoplasmic)
        section_layout.addWidget(self._cyto_run_button)
        section.setLayout(section_layout)
        return section

    def _make_model_settings_section(self, title: str, section_key: str) -> QGroupBox:
        """Build the model settings section container.

        Parameters
        ----------
        title : str
            Section title displayed on the ring.
        section_key : str
            Section identifier used to store the settings layout.

        Returns
        -------
        QGroupBox
            Group box containing model-specific settings.
        """
        return self._make_titled_section(title, section_key)

    def _make_titled_section(self, title: str, section_key: str) -> QGroupBox:
        """Create a titled box that mimics a group box ring.

        Parameters
        ----------
        title : str
            Title displayed on the ring.
        section_key : str
            Section identifier used to store the settings layout.

        Returns
        -------
        QGroupBox
            Group box containing a framed content area.
        """
        section = QGroupBox(title)
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

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setFrameShadow(QFrame.Plain)
        frame.setObjectName("titled-section-frame")
        frame.setStyleSheet(
            "QFrame#titled-section-frame {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "}"
        )

        settings_layout = QVBoxLayout()
        settings_layout.setContentsMargins(10, 12, 10, 10)
        frame.setLayout(settings_layout)

        section_layout = QVBoxLayout()
        section_layout.setContentsMargins(8, 12, 8, 4)
        section_layout.addWidget(frame)
        section.setLayout(section_layout)

        if section_key == "nuclear":
            self._nuclear_model_settings_layout = settings_layout
        else:
            self._cyto_model_settings_layout = settings_layout

        return section

    def _refresh_layer_choices(self) -> None:
        """Populate layer dropdowns from the napari viewer."""
        nuclear_current = self._nuclear_layer_combo.currentText()
        cyto_current = self._cyto_layer_combo.currentText()
        cyto_nuclear_current = self._cyto_nuclear_layer_combo.currentText()

        self._nuclear_layer_combo.clear()
        self._cyto_layer_combo.clear()
        self._cyto_nuclear_layer_combo.clear()
        if self._viewer is None:
            self._nuclear_layer_combo.addItem("Select a layer")
            self._cyto_layer_combo.addItem("Select a layer")
            self._cyto_nuclear_layer_combo.addItem("Select a layer")
            return

        # For nuclear and cytoplasmic layers, use Image layers
        names = [layer.name for layer in self._iter_image_layers()]
        for name in names:
            self._nuclear_layer_combo.addItem(name)
            self._cyto_layer_combo.addItem(name)
        
        # For cytoplasmic nuclear layer, check if model uses nuclear-only mode
        cyto_model_name = self._cyto_model_combo.currentText()
        if cyto_model_name and cyto_model_name != "No models found":
            try:
                model = self._backend.get_model(cyto_model_name)
                modes = model.cytoplasmic_input_modes()
                if modes == ["nuclear"]:
                    # Nuclear-only mode: populate with Labels layers
                    label_names = [layer.name for layer in self._iter_label_layers()]
                    for name in label_names:
                        self._cyto_nuclear_layer_combo.addItem(name)
                else:
                    # Standard mode: populate with Image layers
                    for name in names:
                        self._cyto_nuclear_layer_combo.addItem(name)
            except Exception:
                # Fallback to Image layers if model can't be loaded
                for name in names:
                    self._cyto_nuclear_layer_combo.addItem(name)
        else:
            # No model selected: populate with Image layers
            for name in names:
                self._cyto_nuclear_layer_combo.addItem(name)
        
        self._cyto_nuclear_layer_combo.insertItem(0, "Select a layer")

        self._restore_combo_selection(self._nuclear_layer_combo, nuclear_current)
        self._restore_combo_selection(self._cyto_layer_combo, cyto_current)
        self._restore_combo_selection(
            self._cyto_nuclear_layer_combo, cyto_nuclear_current
        )

    def _refresh_model_choices(self) -> None:
        """Populate the model dropdowns from available model folders."""
        self._nuclear_model_combo.clear()
        self._cyto_model_combo.clear()

        nuclear_names = self._backend.list_model_names(task="nuclear")
        if not nuclear_names:
            self._nuclear_model_combo.addItem("No models found")
        else:
            self._nuclear_model_combo.addItems(nuclear_names)

        cyto_names = self._backend.list_model_names(task="cytoplasmic")
        if not cyto_names:
            self._cyto_model_combo.addItem("No models found")
        else:
            self._cyto_model_combo.addItems(cyto_names)
        
        # Trigger initial model settings update to configure layer filters
        if cyto_names:
            self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())

    def _update_nuclear_model_settings(self, model_name: str) -> None:
        """Rebuild the nuclear model settings area for the selected model.

        Parameters
        ----------
        model_name : str
            Selected model name from the dropdown.
        """
        self._refresh_model_settings_layout(
            self._nuclear_model_settings_layout, model_name
        )

    def _update_cytoplasmic_model_settings(self, model_name: str) -> None:
        """Rebuild the cytoplasmic model settings area for the selected model.

        Parameters
        ----------
        model_name : str
            Selected model name from the dropdown.
        """
        self._refresh_model_settings_layout(
            self._cyto_model_settings_layout, model_name
        )

        if not model_name or model_name == "No models found":
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_combo.setEnabled(False)
            self._cyto_nuclear_layer_combo.setEnabled(False)
            self._cyto_nuclear_label.setText("Nuclear layer")
            return

        model = self._backend.get_model(model_name)
        modes = model.cytoplasmic_input_modes()
        
        # Check if model only uses nuclear input (nuclear-only mode)
        if modes == ["nuclear"]:
            # Hide cytoplasmic layer and label, show only nuclear
            self._cyto_layer_combo.setVisible(False)
            self._cyto_layer_label.setVisible(False)
            self._cyto_nuclear_layer_combo.setEnabled(True)
            self._cyto_nuclear_label.setText("Nuclear layer")
            # For nuclear-only models, populate with Labels layers
            self._refresh_nuclear_labels_for_cyto()
        elif "nuclear+cytoplasmic" in modes:
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_label.setVisible(True)
            self._cyto_layer_combo.setEnabled(True)
            optional = model.cytoplasmic_nuclear_optional()
            suffix = "optional" if optional else "mandatory"
            self._cyto_nuclear_label.setText(f"Nuclear layer ({suffix})")
            self._cyto_nuclear_layer_combo.setEnabled(True)
            # For standard models, populate with Image layers
            self._refresh_nuclear_images_for_cyto()
        else:
            # Only cytoplasmic
            self._cyto_layer_combo.setVisible(True)
            self._cyto_layer_label.setVisible(True)
            self._cyto_layer_combo.setEnabled(True)
            self._cyto_nuclear_label.setText("Nuclear layer")
            self._cyto_nuclear_layer_combo.setEnabled(False)
            # For standard models, populate with Image layers
            self._refresh_nuclear_images_for_cyto()

        self._update_cytoplasmic_run_state(model)

    def _refresh_nuclear_labels_for_cyto(self) -> None:
        """Refresh cytoplasmic nuclear layer combo with Labels layers."""
        current = self._cyto_nuclear_layer_combo.currentText()
        self._cyto_nuclear_layer_combo.clear()
        
        if self._viewer is None:
            self._cyto_nuclear_layer_combo.addItem("Select a layer")
            return
        
        label_names = [layer.name for layer in self._iter_label_layers()]
        for name in label_names:
            self._cyto_nuclear_layer_combo.addItem(name)
        self._cyto_nuclear_layer_combo.insertItem(0, "Select a layer")
        self._restore_combo_selection(self._cyto_nuclear_layer_combo, current)
    
    def _refresh_nuclear_images_for_cyto(self) -> None:
        """Refresh cytoplasmic nuclear layer combo with Image layers."""
        current = self._cyto_nuclear_layer_combo.currentText()
        self._cyto_nuclear_layer_combo.clear()
        
        if self._viewer is None:
            self._cyto_nuclear_layer_combo.addItem("Select a layer")
            return
        
        image_names = [layer.name for layer in self._iter_image_layers()]
        for name in image_names:
            self._cyto_nuclear_layer_combo.addItem(name)
        self._cyto_nuclear_layer_combo.insertItem(0, "Select a layer")
        self._restore_combo_selection(self._cyto_nuclear_layer_combo, current)

    def _iter_label_layers(self) -> list:
        """Iterate over Labels layers in the viewer."""
        if self._viewer is None:
            return []
        
        label_layers = []
        for layer in self._viewer.layers:
            if Labels is not None:
                if isinstance(layer, Labels):
                    label_layers.append(layer)
            else:
                if layer.__class__.__name__ == "Labels":
                    label_layers.append(layer)
        return label_layers

    def _iter_image_layers(self) -> list:
        if self._viewer is None:
            return []

        image_layers = []
        for layer in self._viewer.layers:
            if Image is not None:
                if isinstance(layer, Image):
                    image_layers.append(layer)
            else:
                if layer.__class__.__name__ == "Image":
                    image_layers.append(layer)
        return image_layers

    def _restore_combo_selection(self, combo: QComboBox, name: str) -> None:
        if not name:
            return
        index = combo.findText(name)
        if index != -1:
            combo.setCurrentIndex(index)

    def _refresh_model_settings_layout(
        self,
        settings_layout: QVBoxLayout,
        model_name: str,
    ) -> None:
        """Rebuild the provided model settings area for the selected model.

        Parameters
        ----------
        settings_layout : QVBoxLayout
            Layout to update with model settings controls.
        model_name : str
            Selected model name from the dropdown.
        """
        self._clear_layout(settings_layout)

        if not model_name or model_name == "No models found":
            settings_layout.addWidget(
                QLabel("Select a model to configure its settings.")
            )
            return

        model = self._backend.get_model(model_name)
        settings_map = (
            self._nuclear_settings_widgets
            if settings_layout is self._nuclear_model_settings_layout
            else self._cyto_settings_widgets
        )
        settings_meta = (
            self._nuclear_settings_meta
            if settings_layout is self._nuclear_model_settings_layout
            else self._cyto_settings_meta
        )
        settings_map.clear()
        settings_meta.clear()
        form_layout = self._build_model_settings(
            model, settings_map, settings_meta
        )
        if form_layout is None:
            settings_layout.addWidget(
                QLabel(f"No settings defined for '{model_name}'.")
            )
        else:
            settings_layout.addLayout(form_layout)

    def _update_cytoplasmic_run_state(self, model) -> None:
        """Enable/disable cytoplasmic run button based on required inputs."""
        modes = model.cytoplasmic_input_modes()
        
        # Nuclear-only model: only needs nuclear layer
        if modes == ["nuclear"]:
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            self._cyto_run_button.setEnabled(nuclear_layer is not None)
            return
        
        # Check if nuclear is required
        if self._cyto_requires_nuclear(model):
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            self._cyto_run_button.setEnabled(nuclear_layer is not None)
        else:
            self._cyto_run_button.setEnabled(True)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove widgets and nested layouts from the provided layout.

        Parameters
        ----------
        layout : QVBoxLayout
            Layout to clear.
        """
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            if child_layout is not None:
                self._clear_layout(child_layout)
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_model_settings(
        self, model, settings_map: dict, settings_meta: dict
    ) -> QFormLayout | None:
        """Build model settings controls from model metadata.

        Parameters
        ----------
        model : SenoQuantSegmentationModel
            Model wrapper providing settings metadata.
        settings_map : dict
            Mapping of setting keys to their widgets.
        settings_meta : dict
            Mapping of setting keys to their metadata dictionaries.

        Returns
        -------
        QFormLayout or None
            Form layout containing controls or None if no settings exist.
        """
        settings = model.list_settings()
        if not settings:
            return None

        form_layout = QFormLayout()
        for setting in settings:
            setting_type = setting.get("type")
            label = setting.get("label", setting.get("key", "Setting"))
            key = setting.get("key", label)
            settings_meta[key] = setting

            if setting_type == "float":
                widget = QDoubleSpinBox()
                decimals = int(setting.get("decimals", 1))
                widget.setDecimals(decimals)
                widget.setRange(
                    float(setting.get("min", 0.0)),
                    float(setting.get("max", 1.0)),
                )
                widget.setSingleStep(0.1)
                widget.setValue(float(setting.get("default", 0.0)))
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "int":
                widget = QSpinBox()
                widget.setRange(
                    int(setting.get("min", 0)),
                    int(setting.get("max", 100)),
                )
                widget.setSingleStep(1)
                widget.setValue(int(setting.get("default", 0)))
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(setting.get("default", False)))
                widget.toggled.connect(
                    lambda _checked, m=settings_map, meta=settings_meta: self._apply_setting_dependencies(m, meta)
                )
                settings_map[key] = widget
                form_layout.addRow(label, widget)
            else:
                form_layout.addRow(label, QLabel("Unsupported setting type"))

        self._apply_setting_dependencies(settings_map, settings_meta)

        return form_layout

    def _apply_setting_dependencies(
        self, settings_map: dict, settings_meta: dict
    ) -> None:
        """Apply enabled/disabled relationships between settings."""
        for key, setting in settings_meta.items():
            widget = settings_map.get(key)
            if widget is None:
                continue

            enabled_by = setting.get("enabled_by")
            disabled_by = setting.get("disabled_by")

            if enabled_by:
                controller = settings_map.get(enabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(controller.isChecked())
            if disabled_by:
                controller = settings_map.get(disabled_by)
                if isinstance(controller, QCheckBox):
                    widget.setEnabled(not controller.isChecked())

    def _collect_settings(self, settings_map: dict) -> dict:
        """Collect current values from the settings widgets.

        Parameters
        ----------
        settings_map : dict
            Mapping of setting keys to their widgets.

        Returns
        -------
        dict
            Setting values keyed by setting name.
        """
        values = {}
        for key, widget in settings_map.items():
            if hasattr(widget, "value"):
                values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
        return values

    def _configure_combo(self, combo: QComboBox) -> None:
        """Apply sizing defaults to combo boxes."""
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(20)
        combo.setMinimumWidth(180)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _run_nuclear(self) -> None:
        """Run nuclear segmentation for the selected model."""
        model_name = self._nuclear_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_preloaded_model(model_name)
        settings = self._collect_settings(self._nuclear_settings_widgets)
        layer_name = self._nuclear_layer_combo.currentText()
        layer = self._get_layer_by_name(layer_name)
        if not self._validate_single_channel_layer(layer, "Nuclear layer"):
            return
        self._start_background_run(
            run_button=self._nuclear_run_button,
            run_text="Run",
            task="nuclear",
            run_callable=lambda: model.run(
                task="nuclear",
                layer=layer,
                settings=settings,
            ),
            on_success=lambda result: self._add_labels_layer(
                layer,
                result.get("masks"),
                model_name=model_name,
                label_type="nuc",
            ),
        )

    def _run_cytoplasmic(self) -> None:
        """Run cytoplasmic segmentation for the selected model."""
        model_name = self._cyto_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_preloaded_model(model_name)
        settings = self._collect_settings(self._cyto_settings_widgets)
        modes = model.cytoplasmic_input_modes()
        
        # Handle nuclear-only models
        if modes == ["nuclear"]:
            nuclear_layer = self._get_layer_by_name(
                self._cyto_nuclear_layer_combo.currentText()
            )
            if not self._validate_single_channel_layer(nuclear_layer, "Nuclear layer"):
                return
            self._start_background_run(
                run_button=self._cyto_run_button,
                run_text="Run",
                task="cytoplasmic",
                run_callable=lambda: model.run(
                    task="cytoplasmic",
                    nuclear_layer=nuclear_layer,
                    settings=settings,
                ),
                on_success=lambda result: self._add_labels_layer(
                    nuclear_layer,
                    result.get("masks"),
                    model_name=model_name,
                    label_type="cyto",
                ),
            )
            return
        
        # Standard models: require cytoplasmic layer
        cyto_layer = self._get_layer_by_name(self._cyto_layer_combo.currentText())
        nuclear_layer = self._get_layer_by_name(
            self._cyto_nuclear_layer_combo.currentText()
        )
        if not self._validate_single_channel_layer(cyto_layer, "Cytoplasmic layer"):
            return
        if nuclear_layer is not None and not self._validate_single_channel_layer(
            nuclear_layer, "Nuclear layer"
        ):
            return
        if self._cyto_requires_nuclear(model) and nuclear_layer is None:
            return
        self._start_background_run(
            run_button=self._cyto_run_button,
            run_text="Run",
            task="cytoplasmic",
            run_callable=lambda: model.run(
                task="cytoplasmic",
                cytoplasmic_layer=cyto_layer,
                nuclear_layer=nuclear_layer,
                settings=settings,
            ),
            on_success=lambda result: self._add_labels_layer(
                cyto_layer,
                result.get("masks"),
                model_name=model_name,
                label_type="cyto",
            ),
        )

    def _start_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        task: str,
        run_callable,
        on_success,
    ) -> None:
        """Run a model in a background thread and manage UI state.

        Parameters
        ----------
        run_button : QPushButton
            Button to disable while the background task runs.
        run_text : str
            Label text to restore after completion.
        task : str
            Task name used for error messaging.
        run_callable : callable
            Callable that executes the model run.
        on_success : callable
            Callback invoked with the run result dictionary.
        """
        run_button.setEnabled(False)
        run_button.setText("Running...")

        thread = QThread(self)
        worker = _RunWorker(run_callable)
        worker.moveToThread(thread)

        def handle_success(result: dict) -> None:
            on_success(result)
            self._finish_background_run(run_button, run_text, thread, worker)

        def handle_error(message: str) -> None:
            self._notify(f"{task.capitalize()} run failed: {message}")
            self._finish_background_run(run_button, run_text, thread, worker)

        thread.started.connect(worker.run)
        worker.finished.connect(handle_success)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        self._active_workers.append((thread, worker))
        thread.start()

    def _finish_background_run(
        self,
        run_button: QPushButton,
        run_text: str,
        thread: QThread,
        worker: QObject,
    ) -> None:
        """Restore UI state after a background run completes.

        Parameters
        ----------
        run_button : QPushButton
            Button to restore after completion.
        run_text : str
            Label text to restore on the button.
        thread : QThread
            Background thread being torn down.
        worker : QObject
            Worker object associated with the thread.
        """
        run_button.setEnabled(True)
        run_button.setText(run_text)
        try:
            self._active_workers.remove((thread, worker))
        except ValueError:
            pass


    def _get_layer_by_name(self, name: str):
        """Return a viewer layer with the given name, if it exists.

        Parameters
        ----------
        name : str
            Layer name to locate.

        Returns
        -------
        object or None
            Matching layer object or None if not found.
        """
        if self._viewer is None:
            return None
        for layer in self._viewer.layers:
            if layer.name == name:
                return layer
        return None

    def _validate_single_channel_layer(self, layer, label: str) -> bool:
        """Validate that a layer is single-channel 2D/3D image data.

        Parameters
        ----------
        layer : object or None
            Napari layer to validate.
        label : str
            User-facing label for notifications.

        Returns
        -------
        bool
            True if the layer is valid for single-channel processing.
        """
        if layer is None:
            return False
        if getattr(layer, "rgb", False):
            self._notify(f"{label} must be single-channel (not RGB).")
            return False
        shape = getattr(getattr(layer, "data", None), "shape", None)
        if shape is None:
            return False
        squeezed_ndim = sum(dim != 1 for dim in shape)
        if squeezed_ndim not in (2, 3):
            self._notify(f"{label} must be 2D or 3D single-channel.")
            return False
        return True

    def _notify(self, message: str) -> None:
        """Send a warning notification to the napari console.

        Parameters
        ----------
        message : str
            Notification message to display.
        """
        if (
            show_console_notification is not None
            and Notification is not None
            and NotificationSeverity is not None
        ):
            show_console_notification(
                Notification(message, severity=NotificationSeverity.WARNING)
            )

    def _on_preload_models_changed(self, enabled: bool) -> None:
        """Handle preload setting changes.

        Parameters
        ----------
        enabled : bool
            Whether preloading is enabled.
        """
        if enabled:
            if (
                show_console_notification is not None
                and Notification is not None
                and NotificationSeverity is not None
            ):
                show_console_notification(
                    Notification(
                        "Preloading segmentation models...",
                        severity=NotificationSeverity.INFO,
                    )
                )
            self._backend.preload_models()

    def _cyto_requires_nuclear(self, model) -> bool:
        """Return True when cytoplasmic mode requires a nuclear channel."""
        modes = model.cytoplasmic_input_modes()
        if modes == ["nuclear"]:
            return True
        if "nuclear+cytoplasmic" not in modes:
            return False
        return not model.cytoplasmic_nuclear_optional()

    def _on_cyto_nuclear_layer_changed(self) -> None:
        model_name = self._cyto_model_combo.currentText()
        if not model_name or model_name == "No models found":
            self._cyto_run_button.setEnabled(False)
            return
        model = self._backend.get_model(model_name)
        self._update_cytoplasmic_run_state(model)

    def _add_labels_layer(self, source_layer, masks, model_name: str, label_type: str) -> None:
        if self._viewer is None or source_layer is None or masks is None:
            return
        label_name = f"{source_layer.name}_{model_name}_{label_type}_labels"
        self._viewer.add_labels(
            masks,
            name=label_name,
        )

        # Get the labels layer and set contour = 2
        labels_layer = self._viewer.layers[label_name]
        labels_layer.contour = 2


class _RunWorker(QObject):
    """Worker that executes a callable in a background thread."""

    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, run_callable) -> None:
        """Initialize the worker with a callable.

        Parameters
        ----------
        run_callable : callable
            Callable to execute on the worker thread.
        """
        super().__init__()
        self._run_callable = run_callable

    def run(self) -> None:
        """Execute the callable and emit results."""
        try:
            result = self._run_callable()
        except Exception as exc:  # pragma: no cover - runtime error path
            self.error.emit(str(exc))
            return
        self.finished.emit(result)
