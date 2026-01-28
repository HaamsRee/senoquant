"""Example QtPy widget for napari."""

from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .tabs import BatchTab, QuantificationTab, SegmentationTab, SettingsTab, SpotsTab
from .tabs.settings.backend import SettingsBackend


class SenoQuantWidget(QWidget):
    """Main SenoQuant widget with tabbed UI."""

    def __init__(self, napari_viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._settings_backend = SettingsBackend()

        layout = QVBoxLayout()

        tabs = QTabWidget()
        tabs.addTab(
            SegmentationTab(
                napari_viewer=napari_viewer,
                settings_backend=self._settings_backend,
            ),
            "Segmentation",
        )
        tabs.addTab(SpotsTab(napari_viewer=napari_viewer), "Spots")
        tabs.addTab(QuantificationTab(napari_viewer=napari_viewer), "Quantification")
        tabs.addTab(BatchTab(napari_viewer=napari_viewer), "Batch")
        tabs.addTab(SettingsTab(backend=self._settings_backend), "Settings")

        layout.addWidget(tabs)
        self.setLayout(layout)
