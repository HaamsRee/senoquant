"""Example QtPy widget for napari."""

from qtpy.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget


class ExampleWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self._viewer = napari_viewer

        layout = QVBoxLayout()

        tabs = QTabWidget()
        tabs.addTab(self._make_tab("Nuclear Segmentation"), "Nuclear Segmentation")
        tabs.addTab(self._make_tab("Cytoplasmic Segmentation"), "Cytoplasmic Segmentation")
        tabs.addTab(self._make_tab("Channels"), "Channels")
        tabs.addTab(self._make_tab("Spots"), "Spots")
        tabs.addTab(self._make_tab("Settings"), "Settings")

        layout.addWidget(tabs)
        self.setLayout(layout)

    def _make_tab(self, title: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"{title} content goes here."))
        widget.setLayout(layout)
        return widget
