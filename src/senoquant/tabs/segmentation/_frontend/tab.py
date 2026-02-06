"""Main Segmentation tab widget composition."""

from __future__ import annotations

from qtpy.QtCore import QObject, QThread
from qtpy.QtWidgets import QVBoxLayout, QWidget

from ...settings.backend import SettingsBackend
from ..backend import SegmentationBackend
from .run_mixin import SegmentationRunMixin
from .settings_mixin import SegmentationSettingsMixin
from .ui_mixin import SegmentationUiMixin
from .widgets import Notification, NotificationSeverity, show_console_notification


class SegmentationTab(
    SegmentationUiMixin,
    SegmentationSettingsMixin,
    SegmentationRunMixin,
    QWidget,
):
    """Segmentation tab UI with nuclear and cytoplasmic sections.

    Parameters
    ----------
    backend : SegmentationBackend or None
        Backend instance used to discover and load models.
    napari_viewer : object or None
        napari viewer used to populate layer choices.
    settings_backend : SettingsBackend or None
        Settings store used for preload configuration.
    """

    def __init__(
        self,
        backend: SegmentationBackend | None = None,
        napari_viewer=None,
        settings_backend: SettingsBackend | None = None,
    ) -> None:
        """Create the segmentation tab UI.

        Parameters
        ----------
        backend : SegmentationBackend or None
            Backend instance used to discover and load models.
        napari_viewer : object or None
            napari viewer used to populate layer choices.
        settings_backend : SettingsBackend or None
            Settings store used for preload configuration.
        """
        super().__init__()
        self._backend = backend or SegmentationBackend()
        self._viewer = napari_viewer
        self._nuclear_settings_widgets = {}
        self._cyto_settings_widgets = {}
        self._nuclear_settings_meta = {}
        self._cyto_settings_meta = {}
        self._settings = settings_backend or SettingsBackend()
        self._settings.preload_models_changed.connect(
            self._on_preload_models_changed
        )
        self._active_workers: list[tuple[QThread, QObject]] = []

        layout = QVBoxLayout()
        layout.addWidget(self._make_nuclear_section())
        layout.addWidget(self._make_cytoplasmic_section())
        layout.addStretch(1)
        self.setLayout(layout)

        self._refresh_layer_choices()
        self._refresh_model_choices()
        self._update_nuclear_model_settings(self._nuclear_model_combo.currentText())
        self._update_cytoplasmic_model_settings(self._cyto_model_combo.currentText())

        if self._settings.preload_models_enabled():
            if (
                show_console_notification is not None
                and Notification is not None
                and NotificationSeverity is not None
            ):
                show_console_notification(
                    Notification(
                        "Preloading segmentation models...",
                        severity=NotificationSeverity.INFO,
                    )
                )
            self._backend.preload_models()
