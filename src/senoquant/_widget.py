"""Example QtPy widget for napari."""

from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .tabs import QuantifyTab, SegmentationTab, SettingsTab, SpotsTab


class SenoQuantWidget(QWidget):
    def __init__(self, napari_viewer):
        super().__init__()
        self._viewer = napari_viewer

        layout = QVBoxLayout()

        tabs = QTabWidget()
        tabs.addTab(SegmentationTab(napari_viewer=napari_viewer), "Segmentation")
        tabs.addTab(SpotsTab(), "Spots")
        tabs.addTab(QuantifyTab(), "Quantify")
        tabs.addTab(SettingsTab(), "Settings")

        layout.addWidget(tabs)
        self.setLayout(layout)
