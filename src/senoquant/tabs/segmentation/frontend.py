"""Frontend widget for the Segmentation tab."""

from qtpy.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from .backend import SegmentationBackend


class SegmentationTab(QWidget):
    def __init__(self, backend: SegmentationBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or SegmentationBackend()

        layout = QVBoxLayout()
        layout.addWidget(self._make_section("Nuclear"))
        layout.addWidget(self._make_section("Cytoplasmic"))
        layout.addStretch(1)
        self.setLayout(layout)

    def _make_section(self, name: str) -> QGroupBox:
        section = QGroupBox(f"{name} Segmentation")
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"{name} segmentation controls go here."))
        section.setLayout(layout)
        return section
