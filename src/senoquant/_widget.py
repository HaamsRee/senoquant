"""Example QtPy widget for napari."""

import webbrowser

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

USER_DOCS_BASE_URL = "https://haamsree.github.io/senoquant/user/"


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
        self._tab_help_urls: list[str] = []
        self._help_button = QtWidgets.QPushButton()
        self._help_button.clicked.connect(self._open_current_tab_help)
        self._configure_help_button()

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
        self._add_tab_with_help(self._sennet_portal_tab, "SenNet Portal", "sennet-portal")
        self._add_tab_with_help(self._segmentation_tab, "Segmentation", "segmentation")
        self._add_tab_with_help(self._spots_tab, "Spots", "spots")
        self._add_tab_with_help(self._prediction_tab, "Prediction", "prediction")
        self._add_tab_with_help(self._quantification_tab, "Quantification", "quantification")
        self._add_tab_with_help(self._visualization_tab, "Visualization", "visualization")
        self._add_tab_with_help(self._batch_tab, "Batch", "batch")
        self._add_tab_with_help(self._settings_tab, "Settings", "settings")
        self._install_help_button()

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

    def _add_tab_with_help(self, tab: QWidget, label: str, docs_slug: str) -> None:
        """Add one tab and register the corresponding user-guide URL.

        Parameters
        ----------
        tab : QWidget
            Tab widget to insert.
        label : str
            Visible tab label.
        docs_slug : str
            User docs slug segment under ``/user/``.
        """
        self._tab_widget.addTab(tab, label)
        self._tab_help_urls.append(f"{USER_DOCS_BASE_URL}{docs_slug}/")

    def _configure_help_button(self) -> None:
        """Set help button icon/text affordance with robust test fallback."""
        icon_setter = getattr(self._help_button, "setIcon", None)
        style_getter = getattr(self, "style", None)
        qstyle_class = getattr(QtWidgets, "QStyle", None)
        icon_name = "SP_FileDialogInfoView"
        icon_value = getattr(qstyle_class, icon_name, None) if qstyle_class is not None else None
        icon_applied = False
        if callable(icon_setter) and callable(style_getter) and icon_value is not None:
            style = style_getter()
            standard_icon = getattr(style, "standardIcon", None)
            if callable(standard_icon):
                icon_setter(standard_icon(icon_value))
                icon_applied = True

        self._help_button.setText("" if icon_applied else "Help")
        set_tool_tip = getattr(self._help_button, "setToolTip", None)
        if callable(set_tool_tip):
            set_tool_tip("Open docs for this tab")
        set_accessible_name = getattr(self._help_button, "setAccessibleName", None)
        if callable(set_accessible_name):
            set_accessible_name("Help")

    def _install_help_button(self) -> None:
        """Attach one contextual help button to the tab-bar top-right corner."""
        set_corner_widget = getattr(self._tab_widget, "setCornerWidget", None)
        if callable(set_corner_widget):
            set_corner_widget(self._help_button)

        current_changed = getattr(self._tab_widget, "currentChanged", None)
        connect = getattr(current_changed, "connect", None)
        if callable(connect):
            connect(self._refresh_help_button_state)
        self._refresh_help_button_state()

    def _refresh_help_button_state(self, *_args) -> None:
        """Enable help only when one URL exists for the active tab."""
        self._help_button.setEnabled(self._current_tab_help_url() is not None)

    def _current_tab_help_url(self) -> str | None:
        """Return the active tab help URL when available."""
        current_index_getter = getattr(self._tab_widget, "currentIndex", None)
        tab_index = int(current_index_getter()) if callable(current_index_getter) else 0
        if 0 <= tab_index < len(self._tab_help_urls):
            return self._tab_help_urls[tab_index]
        return None

    def _open_current_tab_help(self) -> None:
        """Open user documentation for the currently selected tab."""
        help_url = self._current_tab_help_url()
        if help_url is None:
            return
        webbrowser.open(help_url, new=2)

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
