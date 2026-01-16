"""Frontend widget for the Spots tab."""

from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from .backend import SpotsBackend


class SpotsTab(QWidget):
    def __init__(self, backend: SpotsBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or SpotsBackend()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Spots content goes here."))
        layout.addStretch(1)
        self.setLayout(layout)
