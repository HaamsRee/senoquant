"""Frontend widget for the Segmentation tab."""

from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QFrame,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
        super().__init__()
        self._backend = backend or SegmentationBackend()
        self._viewer = napari_viewer

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
        self._nuclear_layer_combo = QComboBox()
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
        self._cyto_layer_combo = QComboBox()
        self._cyto_nuclear_layer_combo = QComboBox()
        self._cyto_model_combo = QComboBox()
        self._cyto_model_combo.currentTextChanged.connect(
            self._update_cytoplasmic_model_settings
        )

        form_layout.addRow("Cytoplasmic layer", self._cyto_layer_combo)
        form_layout.addRow("Nuclear layer", self._cyto_nuclear_layer_combo)
        form_layout.addRow("Model", self._cyto_model_combo)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(
            self._make_model_settings_section("Model settings", "cytoplasmic")
        )

        self._cyto_run_button = QPushButton("Run")
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
        self._nuclear_layer_combo.clear()
        self._cyto_layer_combo.clear()
        self._cyto_nuclear_layer_combo.clear()
        if self._viewer is None:
            self._nuclear_layer_combo.addItem("Select a layer")
            self._cyto_layer_combo.addItem("Select a layer")
            self._cyto_nuclear_layer_combo.addItem("Select a layer")
            return

        for layer in self._viewer.layers:
            self._nuclear_layer_combo.addItem(layer.name)
            self._cyto_layer_combo.addItem(layer.name)
            self._cyto_nuclear_layer_combo.addItem(layer.name)

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
            return

        model = self._backend.get_model(model_name)
        modes = model.cytoplasmic_input_modes()
        self._cyto_nuclear_layer_combo.setEnabled(
            "nuclear+cytoplasmic" in modes
        )

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
        while settings_layout.count():
            item = settings_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not model_name or model_name == "No models found":
            settings_layout.addWidget(
                QLabel("Select a model to configure its settings.")
            )
            return

        model = self._backend.get_model(model_name)
        form_layout = self._build_model_settings(model)
        if form_layout is None:
            settings_layout.addWidget(
                QLabel(f"No settings defined for '{model_name}'.")
            )
        else:
            settings_layout.addLayout(form_layout)

    def _build_model_settings(self, model) -> QFormLayout | None:
        """Build model settings controls from model metadata.

        Parameters
        ----------
        model : SenoQuantSegmentationModel
            Model wrapper providing settings metadata.

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
                form_layout.addRow(label, widget)
            else:
                form_layout.addRow(label, QLabel("Unsupported setting type"))

        return form_layout
