"""Frontend widget for the Quantify tab."""

from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from .backend import QuantifyBackend


class QuantifyTab(QWidget):
    def __init__(self, backend: QuantifyBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or QuantifyBackend()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Quantify content goes here."))
        layout.addStretch(1)
        self.setLayout(layout)
