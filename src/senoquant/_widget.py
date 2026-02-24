"""Example QtPy widget for napari."""

import qtpy.QtWidgets as QtWidgets
from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from senoquant.utils.shutdown import ShutdownManager

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
        self._shutdown_manager = ShutdownManager()
        self._shutdown_errors: list[str] = []
        self._application_shutdown_connected = False
        self._tab_widget = QTabWidget()

        layout = QVBoxLayout()

        self._segmentation_tab = SegmentationTab(napari_viewer=napari_viewer)
        self._spots_tab = SpotsTab(napari_viewer=napari_viewer)
        self._batch_tab = BatchTab(napari_viewer=napari_viewer)
        self._prediction_tab = PredictionTab(napari_viewer=napari_viewer)
        self._quantification_tab = QuantificationTab(napari_viewer=napari_viewer)
        self._visualization_tab = VisualizationTab(napari_viewer=napari_viewer)
        self._settings_tab = SettingsTab(
            backend=self._settings_backend,
            segmentation_tab=self._segmentation_tab,
            spots_tab=self._spots_tab,
            batch_tab=self._batch_tab,
        )

        self._sennet_portal_tab = SenNetPortalTab(napari_viewer=napari_viewer)
        self._tab_widget.addTab(self._sennet_portal_tab, "SenNet Portal")
        self._tab_widget.addTab(self._segmentation_tab, "Segmentation")
        self._tab_widget.addTab(self._spots_tab, "Spots")
        self._tab_widget.addTab(self._prediction_tab, "Prediction")
        self._tab_widget.addTab(self._quantification_tab, "Quantification")
        self._tab_widget.addTab(self._visualization_tab, "Visualization")
        self._tab_widget.addTab(self._batch_tab, "Batch")
        self._tab_widget.addTab(self._settings_tab, "Settings")

        layout.addWidget(self._tab_widget)
        self.setLayout(layout)
        self._register_shutdown_target("SenNet Portal", self._sennet_portal_tab)
        self._register_shutdown_target("Segmentation", self._segmentation_tab)
        self._register_shutdown_target("Spots", self._spots_tab)
        self._register_shutdown_target("Prediction", self._prediction_tab)
        self._register_shutdown_target("Quantification", self._quantification_tab)
        self._register_shutdown_target("Visualization", self._visualization_tab)
        self._register_shutdown_target("Batch", self._batch_tab)
        self._register_shutdown_target("Settings", self._settings_tab)
        self._attach_application_shutdown_hook()

    def _register_shutdown_target(self, name: str, target: object) -> None:
        """Register one tab-level shutdown callback when available.

        Parameters
        ----------
        name : str
            Human-readable target name.
        target : object
            Tab/widget instance that may expose cleanup methods.

        Returns
        -------
        None
            Registers callback when a known cleanup method exists.
        """
        callback = self._shutdown_callback_for_target(target)
        if callback is None:
            return
        self._shutdown_manager.register(name, callback)

    @staticmethod
    def _shutdown_callback_for_target(target: object):
        """Return preferred shutdown callback for one target object.

        Parameters
        ----------
        target : object
            Candidate object for shutdown registration.

        Returns
        -------
        callable or None
            Target cleanup callable when available, else ``None``.
        """
        callback = getattr(target, "shutdown", None)
        if callable(callback):
            return callback
        return None

    def _attach_application_shutdown_hook(self) -> None:
        """Attach shutdown execution to the Qt application quit signal.

        Returns
        -------
        None
            Hook is best-effort and no-op when ``QApplication`` is unavailable.
        """
        if self._application_shutdown_connected:
            return
        application_class = getattr(QtWidgets, "QApplication", None)
        if application_class is None:
            return
        application_instance_getter = getattr(application_class, "instance", None)
        if not callable(application_instance_getter):
            return
        application_instance = application_instance_getter()
        if application_instance is None:
            return
        connected = False
        for signal_name in ("lastWindowClosed", "aboutToQuit"):
            signal = getattr(application_instance, signal_name, None)
            connect = getattr(signal, "connect", None)
            if not callable(connect):
                continue
            connect(self._run_global_shutdown)
            connected = True
        self._application_shutdown_connected = connected

    def _run_global_shutdown(self) -> None:
        """Run registered shutdown hooks once and store non-fatal errors.

        Returns
        -------
        None
            Errors are stored on ``self._shutdown_errors`` for diagnostics.
        """
        self._shutdown_errors = self._shutdown_manager.run_once()

    def closeEvent(self, event) -> None:
        """Run global shutdown callbacks before widget teardown."""
        self._run_global_shutdown()
        super_close = getattr(super(), "closeEvent", None)
        if callable(super_close):
            super_close(event)
