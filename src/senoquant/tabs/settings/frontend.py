"""Frontend widget for the Settings tab."""

from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from .backend import SettingsBackend


class SettingsTab(QWidget):
    def __init__(self, backend: SettingsBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or SettingsBackend()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Settings content goes here."))
        layout.addStretch(1)
        self.setLayout(layout)
