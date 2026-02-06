"""UI composition and layer-list behavior mixin for segmentation frontend."""

from __future__ import annotations

from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .widgets import Image, Labels, RefreshingComboBox


class SegmentationUiMixin:
    """UI construction and viewer layer-list behavior for segmentation tab."""

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

        names = [layer.name for layer in self._iter_image_layers()]
        for name in names:
            self._nuclear_layer_combo.addItem(name)
            self._cyto_layer_combo.addItem(name)

        cyto_model_name = self._cyto_model_combo.currentText()
        if cyto_model_name and cyto_model_name != "No models found":
            try:
                model = self._backend.get_model(cyto_model_name)
                modes = model.cytoplasmic_input_modes()
                if modes == ["nuclear"]:
                    label_names = [layer.name for layer in self._iter_label_layers()]
                    for name in label_names:
                        self._cyto_nuclear_layer_combo.addItem(name)
                else:
                    for name in names:
                        self._cyto_nuclear_layer_combo.addItem(name)
            except Exception:
                for name in names:
                    self._cyto_nuclear_layer_combo.addItem(name)
        else:
            for name in names:
                self._cyto_nuclear_layer_combo.addItem(name)

        self._cyto_nuclear_layer_combo.insertItem(0, "Select a layer")

        self._restore_combo_selection(self._nuclear_layer_combo, nuclear_current)
        self._restore_combo_selection(self._cyto_layer_combo, cyto_current)
        self._restore_combo_selection(
            self._cyto_nuclear_layer_combo, cyto_nuclear_current
        )

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
        """Iterate over Image layers in the viewer."""
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
        """Restore combo selection by visible text if present."""
        if not name:
            return
        index = combo.findText(name)
        if index != -1:
            combo.setCurrentIndex(index)

