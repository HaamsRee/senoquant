"""Frontend widget for the Settings tab."""

from qtpy.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from .backend import SettingsBackend


class SettingsTab(QWidget):
    def __init__(self, backend: SettingsBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or SettingsBackend()

        layout = QVBoxLayout()
        self._preload_checkbox = QCheckBox("Preload segmentation models on startup")
        self._preload_checkbox.setChecked(self._backend.preload_models_enabled())
        self._preload_checkbox.toggled.connect(self._backend.set_preload_models)
        layout.addWidget(self._preload_checkbox)
        layout.addStretch(1)
        self.setLayout(layout)
