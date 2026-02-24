"""Example QtPy widget for napari."""

from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .tabs import (
    BatchTab,
    PredictionTab,
    QuantificationTab,
    SenNetPortalTab,
    SegmentationTab,
    SettingsTab,
    SpotsTab,
    VisualizationTab,
)
from .tabs.settings.backend import SettingsBackend


class SenoQuantWidget(QWidget):
    """Main SenoQuant widget with tabbed UI."""

    def __init__(self, napari_viewer):
        super().__init__()
        self._viewer = napari_viewer
        self._settings_backend = SettingsBackend()
        self._sennet_portal_tab = None

        layout = QVBoxLayout()

        tabs = QTabWidget()
        segmentation_tab = SegmentationTab(napari_viewer=napari_viewer)
        spots_tab = SpotsTab(napari_viewer=napari_viewer)
        batch_tab = BatchTab(napari_viewer=napari_viewer)
        settings_tab = SettingsTab(
            backend=self._settings_backend,
            segmentation_tab=segmentation_tab,
            spots_tab=spots_tab,
            batch_tab=batch_tab,
        )

        self._sennet_portal_tab = SenNetPortalTab(napari_viewer=napari_viewer)
        tabs.addTab(self._sennet_portal_tab, "SenNet Portal")
        tabs.addTab(segmentation_tab, "Segmentation")
        tabs.addTab(spots_tab, "Spots")
        tabs.addTab(PredictionTab(napari_viewer=napari_viewer), "Prediction")
        tabs.addTab(QuantificationTab(napari_viewer=napari_viewer), "Quantification")
        tabs.addTab(VisualizationTab(napari_viewer=napari_viewer), "Visualization")
        tabs.addTab(batch_tab, "Batch")
        tabs.addTab(settings_tab, "Settings")

        layout.addWidget(tabs)
        self.setLayout(layout)

    def closeEvent(self, event) -> None:
        """Cancel active SenNet downloads before widget teardown."""
        portal = getattr(self, "_sennet_portal_tab", None)
        cancel = getattr(portal, "cancel_active_downloads", None)
        if callable(cancel):
            cancel()
        super_close = getattr(super(), "closeEvent", None)
        if callable(super_close):
            super_close(event)
