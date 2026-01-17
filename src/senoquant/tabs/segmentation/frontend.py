"""Frontend widget for the Segmentation tab."""

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QFrame,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from napari.layers import Image
except Exception:  # pragma: no cover - optional import for runtime
    Image = None


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


class SegmentationTab(QWidget):
    """Segmentation tab UI with nuclear and cytoplasmic sections.

    Parameters
    ----------
    backend : SegmentationBackend or None
        Backend instance used to discover and load models.
    napari_viewer : object or None
        Napari viewer used to populate layer choices.
    """

    def __init__(
        self,
        backend: SegmentationBackend | None = None,
        napari_viewer=None,
    ) -> None:
        """Create the segmentation tab UI.

        Parameters
        ----------
        backend : SegmentationBackend or None
            Backend instance used to discover and load models.
        napari_viewer : object or None
            Napari viewer used to populate layer choices.
        """
        super().__init__()
        self._backend = backend or SegmentationBackend()
        self._viewer = napari_viewer
        self._nuclear_settings_widgets = {}
        self._cyto_settings_widgets = {}

        layout = QVBoxLayout()
        layout.addWidget(self._make_nuclear_section())
        layout.addWidget(self._make_cytoplasmic_section())
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_layer_choices()
        self._refresh_model_choices()
        self._update_nuclear_model_settings(self._nuclear_model_combo.currentText())
        self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())

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
        self._nuclear_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._nuclear_model_combo = QComboBox()
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
        self._cyto_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._cyto_nuclear_layer_combo = RefreshingComboBox(
            refresh_callback=self._refresh_layer_choices
        )
        self._cyto_nuclear_layer_combo.currentTextChanged.connect(
            self._on_cyto_nuclear_layer_changed
        )
        self._cyto_model_combo = QComboBox()
        self._cyto_model_combo.currentTextChanged.connect(
            self._update_cytoplasmic_model_settings
        )

        form_layout.addRow("Cytoplasmic layer", self._cyto_layer_combo)
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

        names = [layer.name for layer in self._iter_image_layers()]
        for name in names:
            self._nuclear_layer_combo.addItem(name)
            self._cyto_layer_combo.addItem(name)
            self._cyto_nuclear_layer_combo.addItem(name)

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
            self._cyto_nuclear_layer_combo.setEnabled(False)
            self._cyto_nuclear_label.setText("Nuclear layer")
            return

        model = self._backend.get_model(model_name)
        modes = model.cytoplasmic_input_modes()
        if "nuclear+cytoplasmic" in modes:
            optional = model.cytoplasmic_nuclear_optional()
            suffix = "optional" if optional else "mandatory"
            self._cyto_nuclear_label.setText(f"Nuclear layer ({suffix})")
            self._cyto_nuclear_layer_combo.setEnabled(True)
        else:
            self._cyto_nuclear_label.setText("Nuclear layer")
            self._cyto_nuclear_layer_combo.setEnabled(False)

        self._update_cytoplasmic_run_state(model)

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
        settings_map.clear()
        form_layout = self._build_model_settings(model, settings_map)
        if form_layout is None:
            settings_layout.addWidget(
                QLabel(f"No settings defined for '{model_name}'.")
            )
        else:
            settings_layout.addLayout(form_layout)

    def _update_cytoplasmic_run_state(self, model) -> None:
        """Enable/disable cytoplasmic run button based on required inputs."""
        if self._cyto_requires_nuclear(model):
            has_nuclear = bool(self._cyto_nuclear_layer_combo.currentText())
            self._cyto_run_button.setEnabled(has_nuclear)
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

    def _build_model_settings(self, model, settings_map: dict) -> QFormLayout | None:
        """Build model settings controls from model metadata.

        Parameters
        ----------
        model : SenoQuantSegmentationModel
            Model wrapper providing settings metadata.
        settings_map : dict
            Mapping of setting keys to their widgets.

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
                settings_map[setting.get("key", label)] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "int":
                widget = QSpinBox()
                widget.setRange(
                    int(setting.get("min", 0)),
                    int(setting.get("max", 100)),
                )
                widget.setSingleStep(1)
                widget.setValue(int(setting.get("default", 0)))
                settings_map[setting.get("key", label)] = widget
                form_layout.addRow(label, widget)
            elif setting_type == "bool":
                widget = QCheckBox()
                widget.setChecked(bool(setting.get("default", False)))
                settings_map[setting.get("key", label)] = widget
                form_layout.addRow(label, widget)
            else:
                form_layout.addRow(label, QLabel("Unsupported setting type"))

        return form_layout

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
        return values

    def _run_nuclear(self) -> None:
        """Run nuclear segmentation for the selected model."""
        model_name = self._nuclear_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_model(model_name)
        settings = self._collect_settings(self._nuclear_settings_widgets)
        layer_name = self._nuclear_layer_combo.currentText()
        layer = self._get_layer_by_name(layer_name)
        result = model.run(task="nuclear", layer=layer, settings=settings)
        self._add_labels_layer(layer, result.get("masks"), suffix="_nuclear_labels")

    def _run_cytoplasmic(self) -> None:
        """Run cytoplasmic segmentation for the selected model."""
        model_name = self._cyto_model_combo.currentText()
        if not model_name or model_name == "No models found":
            return
        model = self._backend.get_model(model_name)
        settings = self._collect_settings(self._cyto_settings_widgets)
        cyto_layer = self._get_layer_by_name(self._cyto_layer_combo.currentText())
        nuclear_layer = self._get_layer_by_name(
            self._cyto_nuclear_layer_combo.currentText()
        )
        if self._cyto_requires_nuclear(model) and nuclear_layer is None:
            return
        result = model.run(
            task="cytoplasmic",
            cytoplasmic_layer=cyto_layer,
            nuclear_layer=nuclear_layer,
            settings=settings,
        )
        self._add_labels_layer(cyto_layer, result.get("masks"), suffix="_cyto_labels")

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

    def _cyto_requires_nuclear(self, model) -> bool:
        """Return True when cytoplasmic mode requires a nuclear channel."""
        modes = model.cytoplasmic_input_modes()
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

    def _add_labels_layer(self, source_layer, masks, suffix: str) -> None:
        if self._viewer is None or source_layer is None or masks is None:
            return
        self._viewer.add_labels(
            masks,
            name=f"{source_layer.name}{suffix}",
            contour=2,
        )
