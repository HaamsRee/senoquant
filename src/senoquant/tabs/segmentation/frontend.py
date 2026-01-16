"""Frontend widget for the Segmentation tab."""

from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .backend import SegmentationBackend


class SegmentationTab(QWidget):
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
        layout.addWidget(self._make_section("Cytoplasmic"))
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_nuclear_section(self) -> QGroupBox:
        section = QGroupBox("Nuclear Segmentation")
        section_layout = QVBoxLayout()

        form_layout = QFormLayout()
        self._nuclear_layer_combo = QComboBox()
        self._model_combo = QComboBox()
        self._model_combo.currentTextChanged.connect(self._update_model_settings)

        form_layout.addRow("Nuclear layer", self._nuclear_layer_combo)
        form_layout.addRow("Model", self._model_combo)

        self._model_settings_group = QGroupBox("Model settings")
        self._model_settings_layout = QVBoxLayout()
        self._model_settings_group.setLayout(self._model_settings_layout)

        section_layout.addLayout(form_layout)
        section_layout.addWidget(self._model_settings_group)
        section.setLayout(section_layout)

        self._refresh_layer_choices()
        self._refresh_model_choices()
        self._update_model_settings(self._model_combo.currentText())

        return section

    def _make_section(self, name: str) -> QGroupBox:
        section = QGroupBox(f"{name} Segmentation")
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"{name} segmentation controls go here."))
        section.setLayout(layout)
        return section

    def _refresh_layer_choices(self) -> None:
        self._nuclear_layer_combo.clear()
        if self._viewer is None:
            self._nuclear_layer_combo.addItem("Select a layer")
            return

        for layer in self._viewer.layers:
            self._nuclear_layer_combo.addItem(layer.name)

    def _refresh_model_choices(self) -> None:
        self._model_combo.clear()
        names = self._backend.list_model_names()
        if not names:
            self._model_combo.addItem("No models found")
            return

        self._model_combo.addItems(names)

    def _update_model_settings(self, model_name: str) -> None:
        while self._model_settings_layout.count():
            item = self._model_settings_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not model_name or model_name == "No models found":
            self._model_settings_layout.addWidget(
                QLabel("Select a model to configure its settings.")
            )
            return

        self._model_settings_layout.addWidget(
            QLabel(f"Settings for '{model_name}' will appear here.")
        )
